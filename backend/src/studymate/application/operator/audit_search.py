"""Audited inspection search; returned original grants never become caller authority."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from studymate.application.idempotency import IntentFingerprinter
from studymate.application.identity.sessions import SessionCredential, SessionHasher
from studymate.application.operator.audit_search_ports import (
    OperatorAuditCursorCodec,
    OperatorAuditFilters,
    OperatorAuditPosition,
    OperatorAuditSearchUnitOfWork,
    OperatorAuditWindow,
)
from studymate.application.operator.authority import finish_operator, require_operator
from studymate.application.operator.cursors import OperatorCursorScope
from studymate.domain.operator.audit import (
    OPERATOR_EVENT_PAGE_SIZE,
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.operator.timeline import OperatorAuditDetail


@dataclass(frozen=True, slots=True)
class OperatorAuditsPage:
    audits: tuple[OperatorAuditDetail, ...] = field(repr=False)
    next_cursor: str | None
    search_anchor_at: datetime


@dataclass(frozen=True, slots=True)
class SearchOperatorAudits:
    unit_of_work: OperatorAuditSearchUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter
    cursor_codec: OperatorAuditCursorCodec

    async def __call__(
        self,
        credential: SessionCredential,
        filters: OperatorAuditFilters,
        cursor: str | None = None,
    ) -> OperatorAuditsPage:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            now = await transaction.now()
            digest = await self.fingerprinter.fingerprint(filters.fingerprint_parts())
            scope = OperatorCursorScope(principal.access.account_id, principal.access.version)
            position = (
                self.cursor_codec.decode_audits(scope, digest, cursor, now)
                if cursor is not None
                else None
            )
            window = OperatorAuditWindow(
                position.anchor_at if position is not None else now, position
            )
            rows = await transaction.search_audits(filters, window)
            if len(rows) > OPERATOR_EVENT_PAGE_SIZE + 1:
                raise RuntimeError("Audit search exceeded its bounded source page")
            previous = (
                (position.occurred_at, position.audit_id.int) if position is not None else None
            )
            for detail in rows:
                current = detail.audit.at, detail.audit.id.int
                if (
                    detail.audit.at > window.anchor_at
                    or (previous is not None and current >= previous)
                    or not filters.matches(detail)
                ):
                    raise RuntimeError(
                        "Audit search source violated anchored ordering or exact filters"
                    )
                previous = current
            visible = rows[:OPERATOR_EVENT_PAGE_SIZE]
            next_cursor = (
                self.cursor_codec.encode_audits(
                    scope,
                    digest,
                    OperatorAuditPosition(
                        window.anchor_at, visible[-1].audit.at, visible[-1].audit.id
                    ),
                )
                if len(rows) > OPERATOR_EVENT_PAGE_SIZE
                else None
            )
            await transaction.save_operator_audit(
                OperatorAudit(
                    uuid4(),
                    principal.access,
                    OperatorAction.SEARCH_AUDITS,
                    None,
                    tuple(
                        OperatorResourceRef(OperatorResourceKind.AUDIT, row.audit.id)
                        for row in visible
                    ),
                    await transaction.now(),
                    OperatorAuditOutcome.SEARCH,
                    digest,
                )
            )
            await finish_operator(transaction, principal)
            return OperatorAuditsPage(visible, next_cursor, window.anchor_at)
