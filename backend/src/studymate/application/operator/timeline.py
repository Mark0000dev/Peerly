from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from studymate.application.idempotency import IntentFingerprinter
from studymate.application.identity.sessions import SessionCredential, SessionHasher
from studymate.application.operator.authority import finish_operator, require_operator
from studymate.application.operator.cursors import OperatorCursorScope
from studymate.application.operator.timeline_ports import (
    OperatorEventCursorCodec,
    OperatorEventFilters,
    OperatorEventPosition,
    OperatorEventWindow,
    OperatorTimelineUnitOfWork,
)
from studymate.domain.operator.audit import (
    OPERATOR_EVENT_PAGE_SIZE,
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.operator.timeline import OperatorAuditDetail, OperatorTimelineEvent


@dataclass(frozen=True, slots=True)
class OperatorEventsPage:
    events: tuple[OperatorTimelineEvent, ...] = field(repr=False)
    next_cursor: str | None
    search_anchor_at: datetime


@dataclass(frozen=True, slots=True)
class SearchOperatorEvents:
    unit_of_work: OperatorTimelineUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter
    cursor_codec: OperatorEventCursorCodec

    async def __call__(
        self,
        credential: SessionCredential,
        filters: OperatorEventFilters,
        cursor: str | None = None,
    ) -> OperatorEventsPage:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            now = await transaction.now()
            digest = await self.fingerprinter.fingerprint(filters.fingerprint_parts())
            scope = OperatorCursorScope(principal.access.account_id, principal.access.version)
            position = (
                self.cursor_codec.decode_events(scope, digest, cursor, now)
                if cursor is not None
                else None
            )
            window = OperatorEventWindow(
                position.anchor_at if position is not None else now, position
            )
            rows = await transaction.search_events(filters, window)
            if len(rows) > OPERATOR_EVENT_PAGE_SIZE + 1:
                raise RuntimeError("Operator timeline search exceeded its bounded results")
            previous = (
                (position.occurred_at, position.event_id.int) if position is not None else None
            )
            for row in rows:
                current = row.occurred_at, row.id.int
                if row.occurred_at > window.anchor_at or (
                    previous is not None and current >= previous
                ):
                    raise RuntimeError(
                        "Operator event results violate their anchored search ordering"
                    )
                previous = current
            visible = rows[:OPERATOR_EVENT_PAGE_SIZE]
            next_cursor = (
                self.cursor_codec.encode_events(
                    scope,
                    digest,
                    OperatorEventPosition(
                        window.anchor_at, visible[-1].occurred_at, visible[-1].id
                    ),
                )
                if len(rows) > OPERATOR_EVENT_PAGE_SIZE
                else None
            )
            await transaction.save_operator_audit(
                OperatorAudit(
                    uuid4(),
                    principal.access,
                    OperatorAction.SEARCH_EVENTS,
                    None,
                    tuple(
                        OperatorResourceRef(OperatorResourceKind.EVENT, row.id) for row in visible
                    ),
                    await transaction.now(),
                    OperatorAuditOutcome.SEARCH,
                    digest,
                )
            )
            await finish_operator(transaction, principal)
            return OperatorEventsPage(visible, next_cursor, window.anchor_at)


@dataclass(frozen=True, slots=True)
class ReadOperatorEvent:
    unit_of_work: OperatorTimelineUnitOfWork
    hasher: SessionHasher

    async def __call__(
        self, credential: SessionCredential, event_id: UUID
    ) -> OperatorTimelineEvent | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            event = await transaction.operator_event(event_id)
            if event is not None and event.id != event_id:
                raise RuntimeError("Operator event detail differs from its actual requested source")
            requested = OperatorResourceRef(OperatorResourceKind.EVENT, event_id)
            await transaction.save_operator_audit(
                OperatorAudit(
                    uuid4(),
                    principal.access,
                    OperatorAction.READ_EVENT,
                    requested,
                    (requested,) if event is not None else (),
                    await transaction.now(),
                    OperatorAuditOutcome.READ
                    if event is not None
                    else OperatorAuditOutcome.NOT_FOUND,
                )
            )
            await finish_operator(transaction, principal)
            return event


@dataclass(frozen=True, slots=True)
class ReadOperatorAudit:
    unit_of_work: OperatorTimelineUnitOfWork
    hasher: SessionHasher

    async def __call__(
        self, credential: SessionCredential, audit_id: UUID
    ) -> OperatorAuditDetail | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            detail = await transaction.operator_audit(audit_id)
            if detail is not None and detail.audit.id != audit_id:
                raise RuntimeError("Operator audit detail differs from its actual requested source")
            requested = OperatorResourceRef(OperatorResourceKind.AUDIT, audit_id)
            await transaction.save_operator_audit(
                OperatorAudit(
                    uuid4(),
                    principal.access,
                    OperatorAction.READ_AUDIT,
                    requested,
                    (requested,) if detail is not None else (),
                    await transaction.now(),
                    OperatorAuditOutcome.READ
                    if detail is not None
                    else OperatorAuditOutcome.NOT_FOUND,
                )
            )
            await finish_operator(transaction, principal)
            return detail
