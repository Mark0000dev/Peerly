from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, union_all
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.media.resume import RECENT_TERMINAL_UPLOADS, PhotoResumeTransaction
from studymate.application.media.uploads import MAX_PENDING_UPLOADS
from studymate.domain.media import PhotoUpload
from studymate.infrastructure.persistence.media_models import (
    PhotoUploadRecord,
    PhotoUploadRevisionRecord,
)
from studymate.infrastructure.persistence.media_uploads import (
    PENDING_STATES,
    SqlMediaTransaction,
    upload_value,
)
from studymate.infrastructure.persistence.transactions import open_transaction


@dataclass(frozen=True, slots=True)
class SqlPhotoResumeTransaction(SqlMediaTransaction):
    async def resume_uploads(
        self, account_id: UUID, current_upload_id: UUID | None
    ) -> tuple[PhotoUpload, ...]:
        current = (
            select(PhotoUploadRecord.id)
            .join(
                PhotoUploadRevisionRecord,
                (
                    (PhotoUploadRevisionRecord.upload_id == PhotoUploadRecord.id)
                    & (PhotoUploadRevisionRecord.version == PhotoUploadRecord.current_version)
                ),
            )
            .where(PhotoUploadRecord.account_id == account_id)
        )
        pending = current.where(PhotoUploadRevisionRecord.state.in_(PENDING_STATES)).limit(
            MAX_PENDING_UPLOADS
        )
        terminal = (
            current.where(PhotoUploadRevisionRecord.state.not_in(PENDING_STATES))
            .order_by(PhotoUploadRevisionRecord.updated_at.desc(), PhotoUploadRecord.id.desc())
            .limit(RECENT_TERMINAL_UPLOADS)
        )
        published = current.where(PhotoUploadRecord.id == current_upload_id).limit(1)
        selected = union_all(pending, terminal, published).subquery()
        records = (
            await self.session.execute(
                select(PhotoUploadRecord, PhotoUploadRevisionRecord)
                .join(
                    PhotoUploadRevisionRecord,
                    (
                        (PhotoUploadRevisionRecord.upload_id == PhotoUploadRecord.id)
                        & (PhotoUploadRevisionRecord.version == PhotoUploadRecord.current_version)
                    ),
                )
                .where(
                    PhotoUploadRecord.account_id == account_id,
                    PhotoUploadRecord.id.in_(select(selected.c.id)),
                )
                .order_by(PhotoUploadRevisionRecord.updated_at.desc(), PhotoUploadRecord.id.desc())
            )
        ).all()
        return tuple(upload_value(*row) for row in records)


@dataclass(frozen=True, slots=True)
class SqlPhotoResumeUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[PhotoResumeTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlPhotoResumeTransaction(session)
