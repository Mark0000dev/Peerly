"""Summary disclosure through real public-profile authority, never a report reference."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from studymate.application.discovery.profiles import (
    DiscoveryProfileReader,
    authorize_discovery_profile,
)
from studymate.application.identity.sessions import (
    SessionCredential,
    SessionHasher,
    StudentActionDeniedError,
    UnauthenticatedError,
    require_verified_student,
)
from studymate.domain.feedback.summary import FeedbackSummary


class FeedbackSummaryTransaction(DiscoveryProfileReader, Protocol):
    async def feedback_summary(self, target_id: UUID) -> FeedbackSummary: ...


class FeedbackSummaryUnitOfWork(Protocol):
    def transaction(
        self, target_id: UUID | None
    ) -> AbstractAsyncContextManager[FeedbackSummaryTransaction]: ...


@dataclass(frozen=True, slots=True)
class FeedbackSummaryView:
    summary: FeedbackSummary
    publicly_visible: bool


@dataclass(frozen=True, slots=True)
class ReadPublicFeedbackSummary:
    unit_of_work: FeedbackSummaryUnitOfWork
    hasher: SessionHasher

    async def __call__(self, credential: SessionCredential, target_id: UUID) -> FeedbackSummaryView:
        async with self.unit_of_work.transaction(target_id) as transaction:
            actor, _ = await authorize_discovery_profile(
                transaction, credential, self.hasher, target_id
            )
            summary = await transaction.feedback_summary(target_id)
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return FeedbackSummaryView(summary, True)


@dataclass(frozen=True, slots=True)
class ReadOwnFeedbackSummary:
    unit_of_work: FeedbackSummaryUnitOfWork
    hasher: SessionHasher

    async def __call__(self, credential: SessionCredential) -> FeedbackSummaryView:
        async with self.unit_of_work.transaction(None) as transaction:
            actor, _ = await require_verified_student(
                transaction, await self.hasher.digest(credential)
            )
            if not actor.activation_complete:
                raise StudentActionDeniedError
            actor_id = actor.session.account_id
            source = await transaction.profile_source(actor_id)
            if source is not None and source.setup.account_id != actor_id:
                raise RuntimeError("Own feedback summary profile source belongs to another account")
            summary = await transaction.feedback_summary(actor_id)
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return FeedbackSummaryView(summary, source is not None and source.can_make_new_contacts)
