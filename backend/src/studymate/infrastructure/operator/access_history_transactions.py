"""Read retained grant/revoke revisions, including unused and revoked legacy grants."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.operator.access_history_ports import (
    OperatorAccessHistoryHead,
    OperatorAccessHistoryWindow,
)
from studymate.domain.operator.access_history import (
    OPERATOR_ACCESS_HISTORY_PAGE_SIZE,
    OperatorAccessHistoryRevision,
)
from studymate.infrastructure.operator.models import OperatorAccessRevisionRecord
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.transactions import open_transaction


@dataclass(frozen=True, slots=True)
class SqlOperatorAccessHistoryTransaction(SqlOperatorTransaction):
    async def access_history_head(self, account_id: UUID) -> OperatorAccessHistoryHead | None:
        self.checked_access()
        row = (
            await self.session.execute(
                select(
                    AccountRecord.id,
                    func.coalesce(func.max(OperatorAccessRevisionRecord.version), 0),
                )
                .outerjoin(
                    OperatorAccessRevisionRecord,
                    OperatorAccessRevisionRecord.account_id == AccountRecord.id,
                )
                .where(AccountRecord.id == account_id)
                .group_by(AccountRecord.id)
            )
        ).one_or_none()
        return OperatorAccessHistoryHead(row[0], row[1]) if row is not None else None

    async def access_history_revisions(
        self,
        account_id: UUID,
        window: OperatorAccessHistoryWindow,
    ) -> tuple[OperatorAccessHistoryRevision, ...]:
        self.checked_access()
        model = OperatorAccessRevisionRecord
        statement = select(model).where(
            model.account_id == account_id, model.version <= window.anchor_version
        )
        if window.before_version is not None:
            statement = statement.where(model.version < window.before_version)
        rows = await self.session.scalars(
            statement.order_by(model.version.desc()).limit(OPERATOR_ACCESS_HISTORY_PAGE_SIZE + 1)
        )
        return tuple(
            OperatorAccessHistoryRevision(
                row.account_id,
                row.version,
                row.active,
                row.changed_at,
                row.changed_by_id,
                row.http_request_id,
                row.action_id,
                row.trace_id,
                row.span_id,
            )
            for row in rows
        )


@dataclass(frozen=True, slots=True)
class SqlOperatorAccessHistoryUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: OperatorAuditRecorder

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlOperatorAccessHistoryTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlOperatorAccessHistoryTransaction(session, self.recorder)
