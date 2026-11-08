"""Raw owned profile-media metadata; no object storage dependency or student-policy replay."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.operator.photo_ports import (
    OperatorPhotoFilters,
    OperatorPhotoHistoryHead,
    OperatorPhotoHistoryWindow,
    OperatorPhotoUploadRootPosition,
)
from studymate.domain.media import PhotoFailure, PhotoUploadState
from studymate.domain.operator.photo_uploads import (
    MAX_OPERATOR_PHOTO_ATTEMPTS,
    OPERATOR_PHOTO_PAGE_SIZE,
    OperatorMediaOrigin,
    OperatorMediaOriginPhase,
    OperatorPhotoAttempt,
    OperatorPhotoAttemptOutcome,
    OperatorPhotoUploadRevision,
    OperatorPhotoUploadRoot,
    OperatorPublishedPhotoRef,
)
from studymate.domain.operator.timeline import OperatorEventOrigin
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.media_models import (
    PhotoRevisionRecord,
    PhotoUploadRecord,
    PhotoUploadRevisionRecord,
)
from studymate.infrastructure.persistence.media_origin_models import MediaOriginRecord
from studymate.infrastructure.persistence.photo_attempt_models import PhotoAttemptRecord
from studymate.infrastructure.persistence.transactions import open_transaction


def revision_value(row: PhotoUploadRevisionRecord) -> OperatorPhotoUploadRevision:
    return OperatorPhotoUploadRevision(
        row.upload_id,
        row.account_id,
        row.version,
        PhotoUploadState(row.state),
        row.updated_at,
        row.attempt_id,
        PhotoFailure(row.failure) if row.failure is not None else None,
    )


def root_value(
    row: PhotoUploadRecord, revision: PhotoUploadRevisionRecord
) -> OperatorPhotoUploadRoot:
    return OperatorPhotoUploadRoot(
        row.id,
        row.account_id,
        row.current_version,
        row.expected_photo_version,
        row.source_size,
        row.source_digest,
        row.content_type,
        row.created_at,
        row.upload_expires_at,
        row.processing_expires_at,
        revision_value(revision),
    )


def attempt_value(row: PhotoAttemptRecord) -> OperatorPhotoAttempt:
    return OperatorPhotoAttempt(
        row.id,
        row.upload_id,
        row.number,
        row.started_at,
        row.lease_until,
        row.finished_at,
        row.next_attempt_at,
        OperatorPhotoAttemptOutcome(row.outcome),
        PhotoFailure(row.failure) if row.failure is not None else None,
        row.display_width,
        row.display_height,
        row.display_size,
        row.display_digest,
    )


@dataclass(frozen=True, slots=True)
class SqlOperatorPhotoTransaction(SqlOperatorTransaction):
    async def photo_account(self, account_id: UUID) -> UUID | None:
        self.checked_access()
        return await self.session.scalar(
            select(AccountRecord.id).where(AccountRecord.id == account_id)
        )

    async def photo_roots(
        self,
        account_id: UUID,
        filters: OperatorPhotoFilters,
        position: OperatorPhotoUploadRootPosition | None,
    ) -> tuple[OperatorPhotoUploadRoot, ...]:
        self.checked_access()
        statement = (
            select(PhotoUploadRecord, PhotoUploadRevisionRecord)
            .join(
                PhotoUploadRevisionRecord,
                (PhotoUploadRevisionRecord.upload_id == PhotoUploadRecord.id)
                & (PhotoUploadRevisionRecord.account_id == PhotoUploadRecord.account_id)
                & (PhotoUploadRevisionRecord.version == PhotoUploadRecord.current_version),
            )
            .where(PhotoUploadRecord.account_id == account_id)
        )
        if filters.state is not None:
            statement = statement.where(PhotoUploadRevisionRecord.state == filters.state.value)
        if filters.created_from is not None:
            statement = statement.where(PhotoUploadRecord.created_at >= filters.created_from)
        if filters.created_before is not None:
            statement = statement.where(PhotoUploadRecord.created_at < filters.created_before)
        if position is not None:
            statement = statement.where(
                tuple_(PhotoUploadRecord.created_at, PhotoUploadRecord.id)
                <= tuple_(position.anchor_created_at, position.anchor_upload_id),
                tuple_(PhotoUploadRecord.created_at, PhotoUploadRecord.id)
                < tuple_(position.before_created_at, position.before_upload_id),
            )
        rows = await self.session.execute(
            statement.order_by(
                PhotoUploadRecord.created_at.desc(), PhotoUploadRecord.id.desc()
            ).limit(OPERATOR_PHOTO_PAGE_SIZE + 1)
        )
        return tuple(root_value(root, revision) for root, revision in rows)

    async def photo_history_head(
        self, account_id: UUID, upload_id: UUID
    ) -> OperatorPhotoHistoryHead | None:
        roots = await self.photo_roots_for_id(account_id, upload_id)
        if roots is None:
            return None
        latest = await self.session.scalar(
            select(func.max(PhotoUploadRevisionRecord.version)).where(
                PhotoUploadRevisionRecord.upload_id == upload_id,
                PhotoUploadRevisionRecord.account_id == account_id,
            )
        )
        if latest is None:
            raise RuntimeError("Retained photo upload lost its committed revisions")
        return OperatorPhotoHistoryHead(roots, latest)

    async def photo_roots_for_id(
        self, account_id: UUID, upload_id: UUID
    ) -> OperatorPhotoUploadRoot | None:
        self.checked_access()
        row = (
            await self.session.execute(
                select(PhotoUploadRecord, PhotoUploadRevisionRecord)
                .join(
                    PhotoUploadRevisionRecord,
                    (PhotoUploadRevisionRecord.upload_id == PhotoUploadRecord.id)
                    & (PhotoUploadRevisionRecord.account_id == PhotoUploadRecord.account_id)
                    & (PhotoUploadRevisionRecord.version == PhotoUploadRecord.current_version),
                )
                .where(
                    PhotoUploadRecord.account_id == account_id, PhotoUploadRecord.id == upload_id
                )
            )
        ).one_or_none()
        return root_value(row[0], row[1]) if row is not None else None

    async def photo_history_revisions(
        self,
        account_id: UUID,
        upload_id: UUID,
        window: OperatorPhotoHistoryWindow,
    ) -> tuple[OperatorPhotoUploadRevision, ...]:
        self.checked_access()
        statement = select(PhotoUploadRevisionRecord).where(
            PhotoUploadRevisionRecord.account_id == account_id,
            PhotoUploadRevisionRecord.upload_id == upload_id,
            PhotoUploadRevisionRecord.version <= window.anchor_version,
        )
        if window.before_version is not None:
            statement = statement.where(PhotoUploadRevisionRecord.version < window.before_version)
        rows = await self.session.scalars(
            statement.order_by(PhotoUploadRevisionRecord.version.desc()).limit(
                OPERATOR_PHOTO_PAGE_SIZE + 1
            )
        )
        return tuple(revision_value(row) for row in rows)

    async def photo_attempts_current(
        self, account_id: UUID, upload_id: UUID
    ) -> tuple[OperatorPhotoAttempt, ...]:
        self.checked_access()
        rows = await self.session.scalars(
            select(PhotoAttemptRecord)
            .join(
                PhotoUploadRecord,
                PhotoUploadRecord.id == PhotoAttemptRecord.upload_id,
            )
            .where(PhotoUploadRecord.account_id == account_id, PhotoUploadRecord.id == upload_id)
            .order_by(PhotoAttemptRecord.number)
            .limit(MAX_OPERATOR_PHOTO_ATTEMPTS + 1)
        )
        return tuple(attempt_value(row) for row in rows)

    async def photo_origins(
        self, account_id: UUID, upload_id: UUID
    ) -> tuple[OperatorMediaOrigin, ...]:
        self.checked_access()
        rows = await self.session.scalars(
            select(MediaOriginRecord)
            .join(
                PhotoUploadRecord,
                PhotoUploadRecord.id == MediaOriginRecord.upload_id,
            )
            .where(PhotoUploadRecord.account_id == account_id, PhotoUploadRecord.id == upload_id)
            .order_by(MediaOriginRecord.phase)
            .limit(3)
        )
        return tuple(
            OperatorMediaOrigin(
                row.upload_id,
                OperatorMediaOriginPhase(row.phase),
                OperatorEventOrigin(row.request_id, row.action_id, row.trace_id, row.span_id),
                row.recorded_at,
            )
            for row in rows
        )

    async def latest_photo_publication(
        self, account_id: UUID, upload_id: UUID
    ) -> OperatorPublishedPhotoRef | None:
        self.checked_access()
        row = await self.session.scalar(
            select(PhotoRevisionRecord)
            .where(
                PhotoRevisionRecord.account_id == account_id,
                PhotoRevisionRecord.upload_id == upload_id,
            )
            .order_by(PhotoRevisionRecord.version.desc())
            .limit(1)
        )
        return (
            OperatorPublishedPhotoRef(
                row.account_id, row.version, row.upload_id, row.upload_version, row.saved_at
            )
            if row is not None
            else None
        )


@dataclass(frozen=True, slots=True)
class SqlOperatorPhotoUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: OperatorAuditRecorder

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlOperatorPhotoTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlOperatorPhotoTransaction(session, self.recorder)
