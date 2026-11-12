"""Bounded reads of retained lifecycle sources; no current actor/profile substitution."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.operator.lifecycle_history_ports import (
    OperatorLifecycleHistoryHead,
    OperatorLifecycleHistoryWindow,
)
from studymate.domain.lifecycle.states import LifecycleOperation
from studymate.domain.operator.lifecycle_history import (
    OPERATOR_LIFECYCLE_HISTORY_PAGE_SIZE,
    OperatorLifecycleHistoryRevision,
)
from studymate.infrastructure.lifecycle.models import LifecycleRevisionRecord
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.transactions import open_transaction


@dataclass(frozen=True, slots=True)
class SqlOperatorLifecycleHistoryTransaction(SqlOperatorTransaction):
    async def lifecycle_history_head(self, account_id: UUID) -> OperatorLifecycleHistoryHead | None:
        self.checked_access()
        exists = await self.session.scalar(
            select(AccountRecord.id).where(AccountRecord.id == account_id)
        )
        if exists is None:
            return None
        latest = await self.session.scalar(
            select(func.max(LifecycleRevisionRecord.version)).where(
                LifecycleRevisionRecord.account_id == account_id
            )
        )
        return OperatorLifecycleHistoryHead(account_id, latest if latest is not None else 0)

    async def lifecycle_history_revisions(
        self,
        account_id: UUID,
        window: OperatorLifecycleHistoryWindow,
    ) -> tuple[OperatorLifecycleHistoryRevision, ...]:
        self.checked_access()
        model = LifecycleRevisionRecord
        statement = select(model).where(
            model.account_id == account_id, model.version <= window.anchor_version
        )
        if window.before_version is not None:
            statement = statement.where(model.version < window.before_version)
        rows = await self.session.scalars(
            statement.order_by(model.version.desc()).limit(OPERATOR_LIFECYCLE_HISTORY_PAGE_SIZE + 1)
        )
        return tuple(
            OperatorLifecycleHistoryRevision(
                id=row.id,
                account_id=row.account_id,
                version=row.version,
                previous_version=row.previous_version,
                operation=LifecycleOperation(row.operation),
                before_banned_at=row.before_banned_at,
                before_deleted_at=row.before_deleted_at,
                after_banned_at=row.after_banned_at,
                after_deleted_at=row.after_deleted_at,
                changed_at=row.changed_at,
                actor_id=row.actor_id,
                actor_session_id=row.actor_session_id,
                operator_access_version=row.operator_access_version,
                operator_access_active=row.operator_access_active,
                reason=row.reason,
                workflow_id=row.workflow_id,
                http_request_id=row.http_request_id,
                action_id=row.action_id,
                trace_id=row.trace_id,
                span_id=row.span_id,
            )
            for row in rows
        )


@dataclass(frozen=True, slots=True)
class SqlOperatorLifecycleHistoryUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: OperatorAuditRecorder

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlOperatorLifecycleHistoryTransaction]:
        # Audit and canonical event writes share the actual read transaction.
        async with open_transaction(self.sessions) as session:
            yield SqlOperatorLifecycleHistoryTransaction(session, self.recorder)
