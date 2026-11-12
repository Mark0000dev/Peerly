from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import DateTime, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.policy_history.read import (
    PolicyHistoryItem,
    PolicyHistoryPosition,
)
from studymate.domain.registration import PolicyKind, PolicyReference, PolicyVersion
from studymate.infrastructure.persistence.registration_models import PolicyDocumentRecord
from studymate.infrastructure.persistence.transactions import open_transaction


@dataclass(frozen=True, slots=True)
class SqlPolicyHistoryReader:
    session: AsyncSession

    async def now(self) -> datetime:
        return (
            await self.session.execute(select(func.clock_timestamp(type_=DateTime(timezone=True))))
        ).scalar_one()

    async def published_versions(
        self, kind: PolicyKind, before: PolicyHistoryPosition | None, limit: int, as_of: datetime
    ) -> tuple[PolicyHistoryItem, ...]:
        model = PolicyDocumentRecord
        statement = select(model.id, model.version, model.published_at, model.title).where(
            model.kind == kind.value,
            model.published_at <= as_of,
            model.published_at <= func.statement_timestamp(),
        )
        if before is not None:
            statement = statement.where(
                tuple_(model.published_at, model.id) < tuple_(before.published_at, before.id)
            )
        rows = await self.session.execute(
            statement.order_by(model.published_at.desc(), model.id.desc()).limit(limit)
        )
        return tuple(
            PolicyHistoryItem(PolicyReference(id_, kind, PolicyVersion(version), at), title)
            for id_, version, at, title in rows
        )


@dataclass(frozen=True, slots=True)
class SqlPolicyHistoryUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlPolicyHistoryReader]:
        async with open_transaction(self.sessions, read_only=True) as session:
            yield SqlPolicyHistoryReader(session)
