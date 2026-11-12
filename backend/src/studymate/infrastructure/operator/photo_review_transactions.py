"""Short human-review transaction; no student visibility or media history mutation."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import IdentitySnapshot
from studymate.application.operator.photo_review_ports import PhotoReviewIntent, PhotoReviewTarget
from studymate.domain.media import PhotoRevision
from studymate.domain.operator.photo_review import PhotoReviewAction, PhotoReviewRevision
from studymate.domain.operator.timeline import OperatorEventOrigin
from studymate.infrastructure.observability.tracing import current_origin
from studymate.infrastructure.operator.photo_review_models import (
    OperatorPhotoReviewIntentRecord,
    OperatorPhotoReviewRecord,
)
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.media_models import PhotoRecord, PhotoRevisionRecord
from studymate.infrastructure.persistence.transactions import open_transaction


class PhotoReviewEventRecorder(Protocol):
    async def __call__(self, session: AsyncSession, source: PhotoReviewRevision) -> None:
        """Exact source ID is its canonical event ID; never foreground activity."""
        ...


def photo_review_value(
    row: OperatorPhotoReviewRecord, photo: PhotoRevisionRecord
) -> PhotoReviewRevision:
    return PhotoReviewRevision(
        row.id,
        row.account_id,
        row.version,
        row.previous_revision_id,
        PhotoReviewAction(row.action),
        PhotoRevision(photo.account_id, photo.version, photo.upload_id, photo.saved_at),
        row.operator_id,
        row.session_id,
        row.operator_access_version,
        row.decided_at,
        row.reason,
        OperatorEventOrigin(row.http_request_id, row.action_id, row.trace_id, row.span_id),
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class SqlPhotoReviewTransaction(SqlOperatorTransaction):
    target_account_id: UUID
    review_recorder: PhotoReviewEventRecorder

    async def lock_identity(self, secret_digest: bytes) -> IdentitySnapshot | None:
        return await self.lock_identity_for_peer(secret_digest, self.target_account_id)

    async def photo_review_target(self, account_id: UUID) -> PhotoReviewTarget | None:
        self.checked_access()
        if account_id != self.target_account_id:
            raise RuntimeError("Photo review target differs from the ordered account lock")
        if await self.session.get(AccountRecord, account_id) is None:
            return None
        photo = await self.session.scalar(
            select(PhotoRevisionRecord)
            .join(
                PhotoRecord,
                (PhotoRecord.account_id == PhotoRevisionRecord.account_id)
                & (PhotoRecord.current_version == PhotoRevisionRecord.version),
            )
            .where(PhotoRecord.account_id == account_id)
        )
        row = (
            await self.session.execute(
                select(OperatorPhotoReviewRecord, PhotoRevisionRecord)
                .join(
                    PhotoRevisionRecord,
                    (PhotoRevisionRecord.account_id == OperatorPhotoReviewRecord.account_id)
                    & (PhotoRevisionRecord.version == OperatorPhotoReviewRecord.photo_version),
                )
                .where(OperatorPhotoReviewRecord.account_id == account_id)
                .order_by(OperatorPhotoReviewRecord.version.desc())
                .limit(1)
            )
        ).one_or_none()
        return PhotoReviewTarget(
            account_id,
            PhotoRevision(photo.account_id, photo.version, photo.upload_id, photo.saved_at)
            if photo is not None
            else None,
            photo_review_value(*row) if row is not None else None,
        )

    async def prior_photo_review(
        self, operator_id: UUID, key: IntentKey
    ) -> PhotoReviewIntent | None:
        if self.checked_access().account_id != operator_id:
            raise RuntimeError("Photo review intent belongs to another authenticated operator")
        row = (
            await self.session.execute(
                select(
                    OperatorPhotoReviewIntentRecord, OperatorPhotoReviewRecord, PhotoRevisionRecord
                )
                .join(
                    OperatorPhotoReviewRecord,
                    OperatorPhotoReviewRecord.id == OperatorPhotoReviewIntentRecord.revision_id,
                )
                .join(
                    PhotoRevisionRecord,
                    (PhotoRevisionRecord.account_id == OperatorPhotoReviewRecord.account_id)
                    & (PhotoRevisionRecord.version == OperatorPhotoReviewRecord.photo_version),
                )
                .where(
                    OperatorPhotoReviewIntentRecord.operator_id == operator_id,
                    OperatorPhotoReviewIntentRecord.key == key.value,
                )
            )
        ).one_or_none()
        if row is None:
            return None
        intent, source, photo = row
        return PhotoReviewIntent(intent.fingerprint, photo_review_value(source, photo))

    async def save_photo_review(
        self, source: PhotoReviewRevision, key: IntentKey, fingerprint: bytes
    ) -> PhotoReviewRevision:
        access = self.checked_access()
        if source.operator_id != access.account_id or source.grant_version != access.version:
            raise RuntimeError("Photo review proof differs from the actual operator grant")
        if source.account_id != self.target_account_id:
            raise RuntimeError("Photo review proof differs from its ordered target")
        origin = current_origin()
        source = replace(
            source,
            origin=OperatorEventOrigin(
                origin.request_id, origin.action_id, origin.trace_id, origin.span_id
            )
            if origin is not None
            else OperatorEventOrigin(),
        )
        self.session.add(
            OperatorPhotoReviewRecord(
                id=source.id,
                account_id=source.account_id,
                version=source.version,
                previous_revision_id=source.previous_revision_id,
                previous_version=source.version - 1 if source.version > 1 else None,
                action=source.action.value,
                photo_version=source.photo.version,
                operator_id=source.operator_id,
                operator_access_version=source.grant_version,
                operator_access_active=True,
                session_id=source.session_id,
                event_kind="photo.reviewed",
                decided_at=source.decided_at,
                reason=source.reason,
                http_request_id=source.origin.http_request_id,
                action_id=source.origin.action_id,
                trace_id=source.origin.trace_id,
                span_id=source.origin.span_id,
            )
        )
        await self.session.flush()
        await self.review_recorder(self.session, source)
        self.session.add(
            OperatorPhotoReviewIntentRecord(
                operator_id=source.operator_id,
                key=key.value,
                revision_id=source.id,
                fingerprint=fingerprint,
            )
        )
        await self.session.flush()
        return source


@dataclass(frozen=True, slots=True)
class SqlPhotoReviewUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: OperatorAuditRecorder
    review_recorder: PhotoReviewEventRecorder

    @asynccontextmanager
    async def transaction(
        self, actor_secret_digest: bytes, target_account_id: UUID
    ) -> AsyncIterator[SqlPhotoReviewTransaction]:
        async with open_transaction(self.sessions) as session:
            await SqlIdentityTransaction(session).lock_identity_for_peer(
                actor_secret_digest, target_account_id
            )
            yield SqlPhotoReviewTransaction(
                session,
                self.recorder,
                target_account_id=target_account_id,
                review_recorder=self.review_recorder,
            )
