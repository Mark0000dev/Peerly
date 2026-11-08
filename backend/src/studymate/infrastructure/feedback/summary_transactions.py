"""Actual account/session/profile guard and aggregate stay in the same SQL transaction."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.identity.sessions import IdentitySnapshot
from studymate.domain.feedback.summary import FeedbackSummary
from studymate.infrastructure.feedback.summary import read_feedback_summary
from studymate.infrastructure.persistence.discovery_profiles import SqlDiscoveryProfileReader
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.transactions import open_transaction


@dataclass(slots=True)
class SummaryAuthority:
    actor_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class SqlFeedbackSummaryTransaction(SqlDiscoveryProfileReader):
    target_id: UUID | None
    authority: SummaryAuthority = field(default_factory=SummaryAuthority)

    def authenticated(self, account_id: UUID) -> None:
        SqlIdentityTransaction.authenticated(self, account_id)
        self.authority.actor_id = account_id

    async def lock_identity(self, secret_digest: bytes) -> IdentitySnapshot | None:
        if self.target_id is None:
            return await SqlIdentityTransaction.lock_identity(self, secret_digest)
        return await self.lock_identity_for_peer(secret_digest, self.target_id)

    async def feedback_summary(self, target_id: UUID) -> FeedbackSummary:
        actor_id = self.authority.actor_id
        expected = actor_id if self.target_id is None else self.target_id
        if actor_id is None or target_id != expected:
            raise RuntimeError("Feedback summary differs from its actual authenticated SQL scope")
        return await read_feedback_summary(self.session, target_id)


@dataclass(frozen=True, slots=True)
class SqlFeedbackSummaryUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(
        self, target_id: UUID | None
    ) -> AsyncIterator[SqlFeedbackSummaryTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlFeedbackSummaryTransaction(session, target_id)
