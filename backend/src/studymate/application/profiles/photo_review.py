"""Owner-only recovery state; no operator identity, rationale or private case content."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from studymate.application.identity.sessions import (
    IdentityReader,
    SessionCredential,
    SessionHasher,
    UnauthenticatedError,
    require_verified_student,
)
from studymate.domain.operator.photo_review import PhotoReviewRecovery


class OwnPhotoReviewReader(IdentityReader, Protocol):
    async def photo_review_recovery(self, account_id: UUID) -> PhotoReviewRecovery: ...


class OwnPhotoReviewUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[OwnPhotoReviewReader]: ...


@dataclass(frozen=True, slots=True)
class ReadOwnPhotoReview:
    unit_of_work: OwnPhotoReviewUnitOfWork
    hasher: SessionHasher

    async def __call__(self, credential: SessionCredential) -> PhotoReviewRecovery:
        async with self.unit_of_work.transaction() as transaction:
            actor, _ = await require_verified_student(
                transaction, await self.hasher.digest(credential)
            )
            result = await transaction.photo_review_recovery(actor.session.account_id)
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return result
