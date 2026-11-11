"""Actual original-grant joined audit sources; no lifecycle or case gate."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy import and_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.operator.audit_search_ports import (
    OperatorAuditFilters,
    OperatorAuditWindow,
)
from studymate.domain.operator.audit import OPERATOR_EVENT_PAGE_SIZE
from studymate.domain.operator.timeline import OperatorAuditDetail
from studymate.infrastructure.operator.models import (
    OperatorAccessRevisionRecord,
    OperatorAuditRecord,
)
from studymate.infrastructure.operator.timeline_values import audit_value
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.transactions import open_transaction


@dataclass(frozen=True, slots=True)
class SqlOperatorAuditSearchTransaction(SqlOperatorTransaction):
    async def search_audits(
        self, filters: OperatorAuditFilters, window: OperatorAuditWindow
    ) -> tuple[OperatorAuditDetail, ...]:
        self.checked_access()
        statement = select(OperatorAuditRecord, OperatorAccessRevisionRecord).join(
            OperatorAccessRevisionRecord,
            and_(
                OperatorAccessRevisionRecord.account_id == OperatorAuditRecord.operator_id,
                OperatorAccessRevisionRecord.version == OperatorAuditRecord.operator_access_version,
            ),
        )
        statement = statement.where(OperatorAuditRecord.occurred_at <= window.anchor_at)
        if filters.operator_id is not None:
            statement = statement.where(OperatorAuditRecord.operator_id == filters.operator_id)
        if filters.action is not None:
            statement = statement.where(OperatorAuditRecord.action == filters.action.value)
        if filters.requested_kind is not None:
            statement = statement.where(
                OperatorAuditRecord.resource_kind == filters.requested_kind.value,
                OperatorAuditRecord.requested_id.is_not(None),
            )
        if filters.requested_id is not None:
            statement = statement.where(OperatorAuditRecord.requested_id == filters.requested_id)
        if filters.http_request_id is not None:
            statement = statement.where(
                OperatorAuditRecord.http_request_id == filters.http_request_id
            )
        if filters.action_id is not None:
            statement = statement.where(OperatorAuditRecord.action_id == filters.action_id)
        if filters.trace_id is not None:
            statement = statement.where(OperatorAuditRecord.trace_id == filters.trace_id)
        if filters.occurred_from is not None:
            statement = statement.where(OperatorAuditRecord.occurred_at >= filters.occurred_from)
        if filters.occurred_before is not None:
            statement = statement.where(OperatorAuditRecord.occurred_at < filters.occurred_before)
        if window.before is not None:
            statement = statement.where(
                tuple_(OperatorAuditRecord.occurred_at, OperatorAuditRecord.id)
                < tuple_(window.before.occurred_at, window.before.audit_id)
            )
        rows = (
            await self.session.execute(
                statement.order_by(
                    OperatorAuditRecord.occurred_at.desc(), OperatorAuditRecord.id.desc()
                ).limit(OPERATOR_EVENT_PAGE_SIZE + 1)
            )
        ).all()
        return tuple(audit_value(*row) for row in rows)


@dataclass(frozen=True, slots=True)
class SqlOperatorAuditSearchUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: OperatorAuditRecorder

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlOperatorAuditSearchTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlOperatorAuditSearchTransaction(session, self.recorder)
