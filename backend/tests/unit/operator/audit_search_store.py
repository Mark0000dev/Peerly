"""Typed fake sources with actual historical audit/grant metadata."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID

from studymate.application.operator.audit_search_ports import (
    OperatorAuditFilters,
    OperatorAuditWindow,
)
from studymate.domain.operator.access import OperatorAccess
from studymate.domain.operator.audit import (
    OPERATOR_EVENT_PAGE_SIZE,
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.operator.timeline import OperatorAuditDetail, OperatorEventOrigin
from tests.unit.identity_store import NOW
from tests.unit.operator.store import Store

ORIGINAL_GRANT_VERSION = 3
ORIGINAL_OPERATOR = UUID(int=900)
TARGET_ID = UUID(int=700)
REQUEST_ID = UUID(int=800)
ACTION_ID = UUID(int=801)


def original(index: int, *, search: bool = False) -> OperatorAuditDetail:
    ref = OperatorResourceRef(OperatorResourceKind.ACCOUNT, TARGET_ID)
    grant = OperatorAccess(ORIGINAL_OPERATOR, ORIGINAL_GRANT_VERSION, True, NOW - timedelta(days=2))
    return OperatorAuditDetail(
        OperatorAudit(
            UUID(int=index),
            grant,
            OperatorAction.SEARCH_ACCOUNTS if search else OperatorAction.READ_ACCOUNT,
            None if search else ref,
            (ref,),
            NOW - timedelta(hours=1),
            OperatorAuditOutcome.SEARCH if search else OperatorAuditOutcome.READ,
            b"f" * 32 if search else None,
        ),
        OperatorEventOrigin(REQUEST_ID, ACTION_ID, "a" * 32, "b" * 16),
    )


class AuditSearchStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.rows: tuple[OperatorAuditDetail, ...] = ()
        self.forced_rows: tuple[OperatorAuditDetail, ...] | None = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["AuditSearchStore"]:
        async with super().transaction():
            yield self

    async def search_audits(
        self, filters: OperatorAuditFilters, window: OperatorAuditWindow
    ) -> tuple[OperatorAuditDetail, ...]:
        self.queried()
        if self.forced_rows is not None:
            return self.forced_rows
        rows = (
            row
            for row in self.rows
            if row.audit.at <= window.anchor_at
            and (
                window.before is None
                or (row.audit.at, row.audit.id.int)
                < (window.before.occurred_at, window.before.audit_id.int)
            )
            and filters.matches(row)
        )
        return tuple(sorted(rows, key=lambda row: (row.audit.at, row.audit.id.int), reverse=True))[
            : OPERATOR_EVENT_PAGE_SIZE + 1
        ]
