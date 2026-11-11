"""Real retained support metadata reads and existing atomic operator audit."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.selectable import ScalarSelect

from studymate.application.support.operator_inbox_ports import (
    OperatorSupportFilters,
    OperatorSupportHistoryWindow,
    OperatorSupportWindow,
)
from studymate.domain.support.cases import SupportReceipt, SupportStatus, SupportTopic
from studymate.domain.support.operator_inbox import (
    OPERATOR_SUPPORT_PAGE_SIZE,
    OperatorSupportRevision,
    OperatorSupportSummary,
)
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.transactions import open_transaction
from studymate.infrastructure.support.models import SupportCaseRecord, SupportRevisionRecord


def _latest_version() -> ScalarSelect[int]:
    return (
        select(SupportRevisionRecord.version)
        .where(SupportRevisionRecord.case_id == SupportCaseRecord.id)
        .order_by(SupportRevisionRecord.version.desc())
        .limit(1)
        .correlate(SupportCaseRecord)
        .scalar_subquery()
    )


@dataclass(frozen=True, slots=True)
class SqlOperatorSupportInboxTransaction(SqlOperatorTransaction):
    async def search_support_cases(
        self, filters: OperatorSupportFilters, window: OperatorSupportWindow
    ) -> tuple[OperatorSupportSummary, ...]:
        self.checked_access()
        # Select only permitted metadata. Private content/proof columns never enter
        # the result or the inbox application objects, including lookahead.
        statement = (
            select(
                SupportCaseRecord.id,
                SupportCaseRecord.actor_id,
                SupportCaseRecord.topic,
                SupportCaseRecord.received_at,
                SupportRevisionRecord.status,
                SupportRevisionRecord.version,
                SupportRevisionRecord.changed_at,
            )
            .join(
                SupportRevisionRecord,
                (SupportRevisionRecord.case_id == SupportCaseRecord.id)
                & (SupportRevisionRecord.version == _latest_version()),
            )
            .where(SupportCaseRecord.received_at <= window.anchor_at)
        )
        if filters.case_id is not None:
            statement = statement.where(SupportCaseRecord.id == filters.case_id)
        if filters.actor_id is not None:
            statement = statement.where(SupportCaseRecord.actor_id == filters.actor_id)
        if filters.anonymous is not None:
            statement = statement.where(
                SupportCaseRecord.actor_id.is_(None)
                if filters.anonymous
                else SupportCaseRecord.actor_id.is_not(None)
            )
        if filters.topic is not None:
            statement = statement.where(SupportCaseRecord.topic == filters.topic.value)
        if filters.status is not None:
            statement = statement.where(SupportRevisionRecord.status == filters.status.value)
        if filters.received_from is not None:
            statement = statement.where(SupportCaseRecord.received_at >= filters.received_from)
        if filters.received_before is not None:
            statement = statement.where(SupportCaseRecord.received_at < filters.received_before)
        if window.before is not None:
            statement = statement.where(
                tuple_(SupportCaseRecord.received_at, SupportCaseRecord.id)
                < tuple_(window.before.received_at, window.before.case_id)
            )
        rows = (
            await self.session.execute(
                statement.order_by(
                    SupportCaseRecord.received_at.desc(), SupportCaseRecord.id.desc()
                ).limit(OPERATOR_SUPPORT_PAGE_SIZE + 1)
            )
        ).all()
        return tuple(
            OperatorSupportSummary(
                SupportReceipt(case_id, SupportStatus(status), version, received_at, changed_at),
                SupportTopic(topic),
                actor_id,
            )
            for case_id, actor_id, topic, received_at, status, version, changed_at in rows
        )

    async def support_history_head(self, case_id: UUID) -> SupportReceipt | None:
        self.checked_access()
        row = (
            await self.session.execute(
                select(
                    SupportCaseRecord.received_at,
                    SupportRevisionRecord.status,
                    SupportRevisionRecord.version,
                    SupportRevisionRecord.changed_at,
                )
                .join(
                    SupportRevisionRecord,
                    (SupportRevisionRecord.case_id == SupportCaseRecord.id)
                    & (SupportRevisionRecord.version == _latest_version()),
                )
                .where(SupportCaseRecord.id == case_id)
            )
        ).one_or_none()
        if row is None:
            return None
        received_at, status, version, changed_at = row
        return SupportReceipt(case_id, SupportStatus(status), version, received_at, changed_at)

    async def support_history(
        self, case_id: UUID, window: OperatorSupportHistoryWindow
    ) -> tuple[OperatorSupportRevision, ...]:
        self.checked_access()
        statement = (
            select(SupportRevisionRecord, SupportCaseRecord.received_at)
            .join(SupportCaseRecord, SupportCaseRecord.id == SupportRevisionRecord.case_id)
            .where(
                SupportRevisionRecord.case_id == case_id,
                SupportRevisionRecord.version <= window.anchor_version,
            )
        )
        if window.before_version is not None:
            statement = statement.where(SupportRevisionRecord.version < window.before_version)
        rows = (
            await self.session.execute(
                statement.order_by(SupportRevisionRecord.version.desc()).limit(
                    OPERATOR_SUPPORT_PAGE_SIZE + 1
                )
            )
        ).all()
        return tuple(
            OperatorSupportRevision(
                SupportReceipt(
                    case_id, SupportStatus(row.status), row.version, received_at, row.changed_at
                ),
                row.changed_by_id,
                row.operator_access_version,
            )
            for row, received_at in rows
        )


@dataclass(frozen=True, slots=True)
class SqlOperatorSupportInboxUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: OperatorAuditRecorder

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlOperatorSupportInboxTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlOperatorSupportInboxTransaction(session, self.recorder)
