from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID, uuid4

from studymate.application.operator.timeline_ports import OperatorEventFilters, OperatorEventWindow
from studymate.domain.operator.audit import (
    OPERATOR_EVENT_PAGE_SIZE,
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.operator.timeline import (
    OperatorAuditDetail,
    OperatorEventFacts,
    OperatorEventKind,
    OperatorEventOrigin,
    OperatorEventSource,
    OperatorSourceKind,
    OperatorTimelineEvent,
)
from tests.unit.identity_store import NOW
from tests.unit.operator.store import TARGET, Store


def event(*, event_id: UUID | None = None, owner: UUID = TARGET) -> OperatorTimelineEvent:
    return OperatorTimelineEvent(
        event_id or uuid4(),
        owner,
        OperatorEventKind.GOAL_SAVED,
        1,
        NOW - timedelta(hours=1),
        (OperatorEventSource(OperatorSourceKind.GOAL, uuid4(), owner, version=1),),
        OperatorEventFacts(topic_present=True, shared_learning=False),
        OperatorEventOrigin(uuid4(), uuid4(), "a" * 32, "b" * 16),
    )


class TimelineStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.events: tuple[OperatorTimelineEvent, ...] = (event(),)
        self.event_map = {row.id: row for row in self.events}
        self.originals: dict[UUID, OperatorAuditDetail] = {}
        self.event_rows: tuple[OperatorTimelineEvent, ...] | None = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["TimelineStore"]:
        async with Store.transaction(self):
            yield self

    def original_audit(self) -> OperatorAuditDetail:
        assert self.access is not None
        source = OperatorResourceRef(OperatorResourceKind.ACCOUNT, TARGET)
        audit = OperatorAudit(
            uuid4(),
            self.access,
            OperatorAction.READ_ACCOUNT,
            source,
            (source,),
            NOW,
            OperatorAuditOutcome.READ,
        )
        original = OperatorAuditDetail(audit, OperatorEventOrigin())
        self.originals[audit.id] = original
        return original

    async def search_events(
        self, filters: OperatorEventFilters, window: OperatorEventWindow
    ) -> tuple[OperatorTimelineEvent, ...]:
        self.queried()
        if self.event_rows is not None:
            return self.event_rows
        rows = tuple(
            row
            for row in self.events
            if row.occurred_at <= window.anchor_at
            and (
                window.before is None
                or (row.occurred_at, row.id.int)
                < (window.before.occurred_at, window.before.event_id.int)
            )
            and (
                filters.subject_account_id is None
                or row.subject_account_id == filters.subject_account_id
            )
            and (
                filters.http_request_id is None
                or row.origin.http_request_id == filters.http_request_id
            )
            and (filters.action_id is None or row.origin.action_id == filters.action_id)
            and (filters.trace_id is None or row.origin.trace_id == filters.trace_id)
            and (filters.kind is None or row.kind == filters.kind)
            and (filters.occurred_from is None or row.occurred_at >= filters.occurred_from)
            and (filters.occurred_before is None or row.occurred_at < filters.occurred_before)
        )
        return tuple(sorted(rows, key=lambda row: (row.occurred_at, row.id.int), reverse=True))[
            : OPERATOR_EVENT_PAGE_SIZE + 1
        ]

    async def operator_event(self, event_id: UUID) -> OperatorTimelineEvent | None:
        self.queried()
        return self.event_map.get(event_id)

    async def operator_audit(self, audit_id: UUID) -> OperatorAuditDetail | None:
        self.queried()
        return self.originals.get(audit_id)
