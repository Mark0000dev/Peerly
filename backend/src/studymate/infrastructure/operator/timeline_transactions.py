"""Actual bounded canonical timeline SQL; pair with main0038 before execution."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.operator.timeline_ports import OperatorEventFilters, OperatorEventWindow
from studymate.domain.operator.audit import OPERATOR_EVENT_PAGE_SIZE
from studymate.domain.operator.timeline import OperatorAuditDetail, OperatorTimelineEvent
from studymate.infrastructure.operator.models import (
    OperatorAccessRevisionRecord,
    OperatorAuditRecord,
)
from studymate.infrastructure.operator.timeline_values import audit_value, event_value
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.transactions import open_transaction


@dataclass(frozen=True, slots=True)
class SqlOperatorTimelineTransaction(SqlOperatorTransaction):
    async def search_events(
        self, filters: OperatorEventFilters, window: OperatorEventWindow
    ) -> tuple[OperatorTimelineEvent, ...]:
        self.checked_access()
        statement = select(ProductEventRecord).where(
            ProductEventRecord.occurred_at <= window.anchor_at
        )
        if filters.subject_account_id is not None:
            statement = statement.where(
                or_(
                    ProductEventRecord.account_id == filters.subject_account_id,
                    ProductEventRecord.lifecycle_account_id == filters.subject_account_id,
                )
            )
        if filters.http_request_id is not None:
            statement = statement.where(ProductEventRecord.request_id == filters.http_request_id)
        if filters.action_id is not None:
            statement = statement.where(ProductEventRecord.action_id == filters.action_id)
        if filters.trace_id is not None:
            statement = statement.where(ProductEventRecord.trace_id == filters.trace_id)
        if filters.kind is not None:
            statement = statement.where(ProductEventRecord.kind == filters.kind.value)
        if filters.occurred_from is not None:
            statement = statement.where(ProductEventRecord.occurred_at >= filters.occurred_from)
        if filters.occurred_before is not None:
            statement = statement.where(ProductEventRecord.occurred_at < filters.occurred_before)
        if window.before is not None:
            statement = statement.where(
                tuple_(ProductEventRecord.occurred_at, ProductEventRecord.id)
                < tuple_(window.before.occurred_at, window.before.event_id)
            )
        rows = await self.session.scalars(
            statement.order_by(
                ProductEventRecord.occurred_at.desc(), ProductEventRecord.id.desc()
            ).limit(OPERATOR_EVENT_PAGE_SIZE + 1)
        )
        return tuple(event_value(row) for row in rows)

    async def operator_event(self, event_id: UUID) -> OperatorTimelineEvent | None:
        self.checked_access()
        row = await self.session.get(ProductEventRecord, event_id)
        return event_value(row) if row is not None else None

    async def operator_audit(self, audit_id: UUID) -> OperatorAuditDetail | None:
        self.checked_access()
        result = (
            await self.session.execute(
                select(OperatorAuditRecord, OperatorAccessRevisionRecord)
                .join(
                    OperatorAccessRevisionRecord,
                    and_(
                        OperatorAccessRevisionRecord.account_id == OperatorAuditRecord.operator_id,
                        OperatorAccessRevisionRecord.version
                        == OperatorAuditRecord.operator_access_version,
                    ),
                )
                .where(OperatorAuditRecord.id == audit_id)
            )
        ).one_or_none()
        return audit_value(*result) if result is not None else None


@dataclass(frozen=True, slots=True)
class SqlOperatorTimelineUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: OperatorAuditRecorder

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlOperatorTimelineTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlOperatorTimelineTransaction(session, self.recorder)
