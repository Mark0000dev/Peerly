"""Exact retained upload/attempt proof and canonical audit, paired with main0043."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.operator.media_ports import OperatorProfileMediaAudit
from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.operator.profile_media import (
    OperatorProfileMediaRequest,
    OperatorProfileMediaSource,
)
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.media_models import PhotoUploadRecord
from studymate.infrastructure.persistence.photo_attempt_models import PhotoAttemptRecord
from studymate.infrastructure.persistence.transactions import open_transaction


@dataclass(frozen=True, slots=True)
class SqlOperatorProfileMediaTransaction(SqlOperatorTransaction):
    async def profile_media_source(
        self, request: OperatorProfileMediaRequest
    ) -> OperatorProfileMediaSource | None:
        self.checked_access()
        row = (
            await self.session.execute(
                select(
                    PhotoUploadRecord.account_id,
                    PhotoUploadRecord.id,
                    PhotoAttemptRecord.id,
                )
                .join(PhotoAttemptRecord, PhotoAttemptRecord.upload_id == PhotoUploadRecord.id)
                .where(
                    PhotoUploadRecord.id == request.upload_id,
                    PhotoUploadRecord.account_id == request.account_id,
                    PhotoAttemptRecord.id == request.attempt_id,
                )
            )
        ).one_or_none()
        return OperatorProfileMediaSource(row[0], row[1], row[2]) if row is not None else None

    async def save_profile_media_audit(self, inspection: OperatorProfileMediaAudit) -> None:
        ref = OperatorResourceRef(OperatorResourceKind.PROFILE_MEDIA, inspection.request.upload_id)
        await self.save_operator_audit(
            OperatorAudit(
                inspection.id,
                inspection.access,
                OperatorAction.READ_MEDIA,
                ref,
                (ref,) if inspection.outcome == OperatorAuditOutcome.READ else (),
                inspection.at,
                inspection.outcome,
                media_request=inspection.request,
                actual_source_upload_id=inspection.actual_source_upload_id,
            )
        )


@dataclass(frozen=True, slots=True)
class SqlOperatorProfileMediaUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: OperatorAuditRecorder

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlOperatorProfileMediaTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlOperatorProfileMediaTransaction(session, self.recorder)
