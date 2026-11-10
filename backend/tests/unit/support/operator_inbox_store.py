import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from studymate.application.errors import StorageUnavailableError
from studymate.application.support.operator_inbox_ports import (
    OperatorSupportFilters,
    OperatorSupportHistoryWindow,
    OperatorSupportWindow,
)
from studymate.domain.operator.audit import OperatorAudit
from studymate.domain.support.cases import SupportReceipt
from studymate.domain.support.operator_inbox import (
    OPERATOR_SUPPORT_PAGE_SIZE,
    OperatorSupportRevision,
    OperatorSupportSummary,
)
from tests.unit.operator.store import Store


class InboxStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.cases: tuple[OperatorSupportSummary, ...] = ()
        self.revisions: dict[UUID, tuple[OperatorSupportRevision, ...]] = {}
        self.forced_rows: tuple[OperatorSupportSummary, ...] | None = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["InboxStore"]:
        async with Store.transaction(self):
            yield self

    async def search_support_cases(
        self, filters: OperatorSupportFilters, window: OperatorSupportWindow
    ) -> tuple[OperatorSupportSummary, ...]:
        self.queried()
        if self.forced_rows is not None:
            return self.forced_rows
        rows = tuple(
            row
            for row in self.cases
            if row.receipt.received_at <= window.anchor_at
            and (
                window.before is None
                or (row.receipt.received_at, row.receipt.case_id.int)
                < (window.before.received_at, window.before.case_id.int)
            )
            and (filters.case_id is None or row.receipt.case_id == filters.case_id)
            and (filters.actor_id is None or row.actor_id == filters.actor_id)
            and (filters.anonymous is None or (row.actor_id is None) == filters.anonymous)
            and (filters.topic is None or row.topic == filters.topic)
            and (filters.status is None or row.receipt.status == filters.status)
            and (filters.received_from is None or row.receipt.received_at >= filters.received_from)
            and (
                filters.received_before is None or row.receipt.received_at < filters.received_before
            )
        )
        return tuple(
            sorted(
                rows,
                key=lambda row: (row.receipt.received_at, row.receipt.case_id.int),
                reverse=True,
            )
        )[: OPERATOR_SUPPORT_PAGE_SIZE + 1]

    async def support_history_head(self, case_id: UUID) -> SupportReceipt | None:
        self.queried()
        rows = self.revisions.get(case_id, ())
        return max((row.receipt for row in rows), key=lambda row: row.version) if rows else None

    async def support_history(
        self, case_id: UUID, window: OperatorSupportHistoryWindow
    ) -> tuple[OperatorSupportRevision, ...]:
        self.queried()
        rows = tuple(
            row
            for row in self.revisions[case_id]
            if row.receipt.version <= window.anchor_version
            and (window.before_version is None or row.receipt.version < window.before_version)
        )
        return tuple(sorted(rows, key=lambda row: row.receipt.version, reverse=True))[
            : OPERATOR_SUPPORT_PAGE_SIZE + 1
        ]


class AuditCancellationStore(InboxStore):
    def __init__(self) -> None:
        super().__init__()
        self.audit_started = asyncio.Event()
        self.audit_release = asyncio.Event()

    async def save_operator_audit(self, audit: OperatorAudit) -> None:
        await super().save_operator_audit(audit)
        self.audit_started.set()
        await self.audit_release.wait()


class CommitFailureStore(InboxStore):
    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["CommitFailureStore"]:
        async with InboxStore.transaction(self):
            yield self
            raise StorageUnavailableError
