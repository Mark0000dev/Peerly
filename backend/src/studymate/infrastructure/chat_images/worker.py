"""Uncomposed SQL image preparation; runtime and canonical provenance remain pending."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.chat_images.worker import (
    MAX_ATTEMPTS,
    ChatImageInfo,
    ChatImageLease,
    ChatImageProcessingStep,
    ChatImageWorkerTransaction,
)
from studymate.domain.chat_images import ChatImageFailure, ChatImagePreparation, ChatImageState
from studymate.infrastructure.chat_images.models import (
    ChatImageAttemptRecord,
    ChatImageRecord,
    ChatImageRevisionRecord,
)
from studymate.infrastructure.chat_images.origins import read_image_queue_origin
from studymate.infrastructure.chat_images.revisions import image_value, save_image_revision
from studymate.infrastructure.observability.media import record_media_claim
from studymate.infrastructure.persistence.conversation_models import ConversationRecord
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
)
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.message_models import MessageOperationRecord
from studymate.infrastructure.persistence.onboarding_models import ProfileActivationRecord
from studymate.infrastructure.persistence.profile_sources import read_blocked_peers
from studymate.infrastructure.persistence.transactions import open_transaction

CLAIM_CANDIDATES = 10


@dataclass(frozen=True, slots=True)
class _LockedImage:
    root: ChatImageRecord = field(repr=False)
    image: ChatImagePreparation = field(repr=False)
    attempt: ChatImageAttemptRecord | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class _AttemptUpdate:
    outcome: Literal["ready", "retry", "rejected", "stale", "interrupted"]
    failure: ChatImageFailure | None = None
    retry_at: datetime | None = None
    info: ChatImageInfo | None = field(default=None, repr=False)


def _finish_attempt(attempt: ChatImageAttemptRecord, update: _AttemptUpdate, at: datetime) -> None:
    if attempt.outcome == "processing":
        attempt.outcome = update.outcome
        attempt.finished_at = at
        attempt.failure = update.failure.value if update.failure is not None else None
        attempt.next_attempt_at = update.retry_at
    if update.info is not None and attempt.display_digest is None:
        attempt.display_width, attempt.display_height = update.info.width, update.info.height
        attempt.display_size = update.info.display_size
        attempt.display_digest = update.info.display_digest


def _fenced(lease: ChatImageLease, current: _LockedImage, at: datetime) -> bool:
    return (
        current.image == lease.image
        and current.attempt is not None
        and current.attempt.id == lease.attempt_id
        and current.attempt.outcome == "processing"
        and at < current.attempt.lease_until
        and at < current.image.processing_expires_at
    )


@dataclass(frozen=True, slots=True)
class SqlChatImageWorkerTransaction:
    session: AsyncSession

    async def now(self) -> datetime:
        return await SqlIdentityTransaction(self.session).now()

    async def _locked(self, image_id: UUID, *, skip_busy: bool) -> _LockedImage | None:
        candidate = await self.session.get(ChatImageRecord, image_id)
        if candidate is None:
            return None
        pair = (candidate.low_id, candidate.high_id)
        acquired = tuple(
            await self.session.scalars(
                select(AccountRecord.id)
                .where(AccountRecord.id.in_(pair))
                .order_by(AccountRecord.id)
                .with_for_update(skip_locked=skip_busy)
            )
        )
        if acquired != pair:
            return None
        conversation = await self.session.scalar(
            select(ConversationRecord.id)
            .where(
                ConversationRecord.id == candidate.conversation_id,
                ConversationRecord.low_id == candidate.low_id,
                ConversationRecord.high_id == candidate.high_id,
            )
            .with_for_update(skip_locked=skip_busy)
        )
        if conversation is None:
            return None
        root, revision = ChatImageRecord, ChatImageRevisionRecord
        row = (
            await self.session.execute(
                select(root, revision)
                .join(
                    revision,
                    (revision.image_id == root.id) & (revision.version == root.current_version),
                )
                .where(root.id == image_id)
                .with_for_update(of=root, skip_locked=skip_busy)
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
        if row is None:
            return None
        image = image_value(*row)
        attempt = None
        if image.attempt_id is not None:
            attempt = (
                await self.session.scalars(
                    select(ChatImageAttemptRecord)
                    .where(
                        ChatImageAttemptRecord.id == image.attempt_id,
                        ChatImageAttemptRecord.image_id == image.id,
                    )
                    .with_for_update()
                )
            ).one()
        return _LockedImage(row[0], image, attempt)

    async def _allowed(self, current: _LockedImage) -> ChatImageFailure | None:
        root = current.root
        pair = (root.low_id, root.high_id)
        active = frozenset(
            await self.session.scalars(
                select(AccountRecord.id)
                .join(
                    InstitutionalBindingRecord,
                    InstitutionalBindingRecord.account_id == AccountRecord.id,
                )
                .join(
                    ProfileActivationRecord, ProfileActivationRecord.account_id == AccountRecord.id
                )
                .where(
                    AccountRecord.id.in_(pair),
                    AccountRecord.deleted_at.is_(None),
                    AccountRecord.banned_at.is_(None),
                    InstitutionalBindingRecord.revoked_at.is_(None),
                )
            )
        )
        if root.account_id not in active:
            return ChatImageFailure.ACCOUNT_UNAVAILABLE
        peer = root.high_id if root.account_id == root.low_id else root.low_id
        if peer not in active or peer in await read_blocked_peers(
            self.session, root.account_id, (peer,)
        ):
            return ChatImageFailure.CONTACT_UNAVAILABLE
        return None

    async def _store(
        self, current: _LockedImage, value: ChatImagePreparation, update: _AttemptUpdate
    ) -> None:
        if current.attempt is not None:
            _finish_attempt(current.attempt, update, value.updated_at)
            await self.session.flush()
        await save_image_revision(self.session, value)

    async def _settle(
        self, current: _LockedImage, at: datetime, info: ChatImageInfo | None = None
    ) -> ChatImageProcessingStep | None:
        value = current.image
        if not value.pending:
            return ChatImageProcessingStep.STALE
        expired = value.expire(at)
        if expired is not value:
            await self._store(current, expired, _AttemptUpdate("interrupted", info=info))
            return ChatImageProcessingStep.EXPIRED
        terminal = await self.session.scalar(
            select(MessageOperationRecord.id).where(
                MessageOperationRecord.author_id == value.account_id,
                MessageOperationRecord.conversation_id == value.conversation_id,
                MessageOperationRecord.client_message_id == value.client_message_id,
            )
        )
        if terminal is not None:
            await self._store(current, value.cancel(at), _AttemptUpdate("interrupted", info=info))
            return ChatImageProcessingStep.STALE
        failure = await self._allowed(current)
        if failure is not None:
            await self._store(
                current, value.reject(failure, at), _AttemptUpdate("rejected", failure, info=info)
            )
            return ChatImageProcessingStep.REJECTED
        return None

    async def expire_images(self, at: datetime, batch: int) -> None:
        root, revision = ChatImageRecord, ChatImageRevisionRecord
        candidates = tuple(
            await self.session.scalars(
                select(root.id)
                .join(
                    revision,
                    (revision.image_id == root.id) & (revision.version == root.current_version),
                )
                .where(
                    or_(
                        and_(revision.state == "uploading", root.upload_expires_at <= at),
                        and_(
                            revision.state.in_(("queued", "processing")),
                            root.processing_expires_at <= at,
                        ),
                    )
                )
                .order_by(root.id)
                .limit(batch)
            )
        )
        for image_id in candidates:
            current = await self._locked(image_id, skip_busy=True)
            if current is not None:
                expired = current.image.expire(max(at, await self.now()))
                if expired is not current.image:
                    await self._store(current, expired, _AttemptUpdate("interrupted"))

    async def claim(
        self, at: datetime, lease_until: datetime
    ) -> ChatImageLease | ChatImageProcessingStep | None:
        duration = lease_until - at
        root, revision, attempt = ChatImageRecord, ChatImageRevisionRecord, ChatImageAttemptRecord
        candidates = tuple(
            await self.session.scalars(
                select(root.id)
                .join(
                    revision,
                    (revision.image_id == root.id) & (revision.version == root.current_version),
                )
                .outerjoin(attempt, attempt.id == revision.attempt_id)
                .where(
                    root.processing_expires_at > at,
                    or_(
                        and_(
                            revision.state == "queued",
                            or_(attempt.id.is_(None), attempt.next_attempt_at <= at),
                        ),
                        and_(revision.state == "processing", attempt.lease_until <= at),
                    ),
                )
                .order_by(root.created_at, root.id)
                .limit(CLAIM_CANDIDATES)
            )
        )
        for image_id in candidates:
            current = await self._locked(image_id, skip_busy=True)
            if current is None:
                continue
            now = max(at, await self.now())
            settled = await self._settle(current, now)
            if settled is not None:
                return settled
            previous = current.attempt
            if current.image.state == ChatImageState.PROCESSING:
                if previous is None or previous.lease_until > now:
                    continue
            elif current.image.state != ChatImageState.QUEUED or (
                previous is not None
                and (previous.next_attempt_at is None or previous.next_attempt_at > now)
            ):
                continue
            number = previous.number + 1 if previous is not None else 1
            if previous is not None:
                _finish_attempt(previous, _AttemptUpdate("interrupted"), now)
            if number > MAX_ATTEMPTS:
                await self._store(
                    current,
                    current.image.reject(ChatImageFailure.PROCESSING_UNAVAILABLE, now),
                    _AttemptUpdate("interrupted", ChatImageFailure.PROCESSING_UNAVAILABLE),
                )
                return ChatImageProcessingStep.REJECTED
            attempt_id = uuid4()
            self.session.add(
                ChatImageAttemptRecord(
                    id=attempt_id,
                    image_id=image_id,
                    number=number,
                    started_at=now,
                    lease_until=now + duration,
                    outcome="processing",
                )
            )
            await self.session.flush()
            processing = current.image.claim(attempt_id, now)
            await save_image_revision(self.session, processing)
            record_media_claim(
                image_id,
                processing.account_id,
                attempt_id,
                number,
                await read_image_queue_origin(self.session, image_id),
            )
            return ChatImageLease(processing, attempt_id, number)
        return None

    async def _stale(
        self,
        lease: ChatImageLease,
        current: _LockedImage,
        at: datetime,
        info: ChatImageInfo | None = None,
    ) -> ChatImageProcessingStep:
        attempt = (
            await self.session.scalars(
                select(ChatImageAttemptRecord)
                .where(
                    ChatImageAttemptRecord.id == lease.attempt_id,
                    ChatImageAttemptRecord.image_id == lease.image.id,
                )
                .with_for_update()
            )
        ).one()
        _finish_attempt(attempt, _AttemptUpdate("stale", info=info), at)
        expired = current.image.expire(at)
        if expired is not current.image:
            await self._store(current, expired, _AttemptUpdate("interrupted"))
            return ChatImageProcessingStep.EXPIRED
        return ChatImageProcessingStep.STALE

    async def preflight(
        self, lease: ChatImageLease, at: datetime
    ) -> ChatImageProcessingStep | None:
        current = await self._locked(lease.image.id, skip_busy=False)
        if current is None:
            return ChatImageProcessingStep.STALE
        at = max(at, await self.now())
        if not _fenced(lease, current, at):
            return await self._stale(lease, current, at)
        return await self._settle(current, at)

    async def complete(
        self, lease: ChatImageLease, image: ChatImageInfo, at: datetime
    ) -> ChatImageProcessingStep:
        current = await self._locked(lease.image.id, skip_busy=False)
        if current is None:
            return ChatImageProcessingStep.STALE
        at = max(at, await self.now())
        if not _fenced(lease, current, at):
            return await self._stale(lease, current, at, image)
        stopped = await self._settle(current, at, image)
        if stopped is not None:
            return stopped
        await self._store(
            current, current.image.ready(lease.attempt_id, at), _AttemptUpdate("ready", info=image)
        )
        return ChatImageProcessingStep.READY

    async def reject(
        self,
        lease: ChatImageLease,
        reason: ChatImageFailure,
        at: datetime,
        retry_at: datetime | None = None,
    ) -> ChatImageProcessingStep:
        current = await self._locked(lease.image.id, skip_busy=False)
        if current is None:
            return ChatImageProcessingStep.STALE
        now = max(at, await self.now())
        if not _fenced(lease, current, now):
            return await self._stale(lease, current, now)
        stopped = await self._settle(current, now)
        if stopped is not None:
            return stopped
        retry = now + (retry_at - at) if retry_at is not None and retry_at > at else None
        if (
            retry is not None
            and retry < current.image.processing_expires_at
            and lease.attempts < MAX_ATTEMPTS
        ):
            await self._store(
                current, current.image.retry(now), _AttemptUpdate("retry", reason, retry)
            )
            return ChatImageProcessingStep.RETRY
        await self._store(
            current, current.image.reject(reason, now), _AttemptUpdate("rejected", reason)
        )
        return ChatImageProcessingStep.REJECTED


@dataclass(frozen=True, slots=True)
class SqlChatImageWorkerUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[ChatImageWorkerTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlChatImageWorkerTransaction(session)
