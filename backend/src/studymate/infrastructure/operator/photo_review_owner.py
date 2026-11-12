"""Read-only owner recovery projection, independent of operator inspection authority."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.domain.media import PhotoRevision
from studymate.domain.operator.photo_review import PhotoReviewRecovery, photo_review_recovery
from studymate.infrastructure.operator.photo_review_models import OperatorPhotoReviewRecord
from studymate.infrastructure.operator.photo_review_transactions import photo_review_value
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.media_models import PhotoRecord, PhotoRevisionRecord
from studymate.infrastructure.persistence.transactions import open_transaction


@dataclass(frozen=True, slots=True)
class SqlOwnPhotoReviewReader(SqlIdentityTransaction):
    async def photo_review_recovery(self, account_id: UUID) -> PhotoReviewRecovery:
        latest = (
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
        if latest is None:
            return photo_review_recovery(None, None)
        current = await self.session.scalar(
            select(PhotoRevisionRecord)
            .join(
                PhotoRecord,
                (PhotoRecord.account_id == PhotoRevisionRecord.account_id)
                & (PhotoRecord.current_version == PhotoRevisionRecord.version),
            )
            .where(PhotoRecord.account_id == account_id)
        )
        return photo_review_recovery(
            photo_review_value(*latest),
            PhotoRevision(current.account_id, current.version, current.upload_id, current.saved_at)
            if current is not None
            else None,
        )


@dataclass(frozen=True, slots=True)
class SqlOwnPhotoReviewUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlOwnPhotoReviewReader]:
        async with open_transaction(self.sessions, read_only=True) as session:
            yield SqlOwnPhotoReviewReader(session, shared_identity_locks=True)
