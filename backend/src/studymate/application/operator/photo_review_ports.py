"""Ordered account/source transaction for explicit human photo decisions."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from studymate.application.idempotency import IntentKey
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.media import PhotoRevision
from studymate.domain.operator.photo_review import PhotoReviewRevision


@dataclass(frozen=True, slots=True)
class PhotoReviewTarget:
    account_id: UUID
    current_photo: PhotoRevision | None
    current_review: PhotoReviewRevision | None


@dataclass(frozen=True, slots=True)
class PhotoReviewIntent:
    fingerprint: bytes = field(repr=False)
    result: PhotoReviewRevision


class PhotoReviewTransaction(OperatorAuditTransaction, Protocol):
    async def photo_review_target(self, account_id: UUID) -> PhotoReviewTarget | None:
        """Lock source; return only actual current READY owned publication and review."""
        ...

    async def prior_photo_review(
        self, operator_id: UUID, key: IntentKey
    ) -> PhotoReviewIntent | None: ...

    async def save_photo_review(
        self, source: PhotoReviewRevision, key: IntentKey, fingerprint: bytes
    ) -> PhotoReviewRevision:
        """Atomic immutable review, canonical event and actor-bound intent.

        No photo/media purge, session change, fake READ audit, account ban or hidden
        mutation. Existing pending requests must not be closed by this condition.
        Return the same source enriched only with its actual execution origin.
        """
        ...


class PhotoReviewUnitOfWork(Protocol):
    def transaction(
        self, actor_secret_digest: bytes, target_account_id: UUID
    ) -> AbstractAsyncContextManager[PhotoReviewTransaction]:
        """Sorted account locks, then live session/grant, then publication/review source."""
        ...
