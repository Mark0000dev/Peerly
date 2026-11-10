"""Explicit privileged support discovery and retained status history."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from studymate.application.idempotency import IntentFingerprinter
from studymate.application.identity.sessions import SessionCredential, SessionHasher
from studymate.application.operator.authority import finish_operator, require_operator
from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.support.operator_inbox_ports import (
    OperatorSupportFilters,
    OperatorSupportHistoryPosition,
    OperatorSupportHistoryWindow,
    OperatorSupportInboxCursorCodec,
    OperatorSupportInboxUnitOfWork,
    OperatorSupportPosition,
    OperatorSupportWindow,
)
from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.support.operator_inbox import (
    OPERATOR_SUPPORT_PAGE_SIZE,
    OperatorSupportRevision,
    OperatorSupportSummary,
)


@dataclass(frozen=True, slots=True)
class OperatorSupportInboxPage:
    cases: tuple[OperatorSupportSummary, ...]
    next_cursor: str | None
    metadata_anchor: datetime


@dataclass(frozen=True, slots=True)
class OperatorSupportHistoryPage:
    case_id: UUID
    anchor_version: int
    revisions: tuple[OperatorSupportRevision, ...]
    next_cursor: str | None


def _validate_inbox(
    rows: tuple[OperatorSupportSummary, ...],
    filters: OperatorSupportFilters,
    window: OperatorSupportWindow,
) -> None:
    if len(rows) > OPERATOR_SUPPORT_PAGE_SIZE + 1:
        raise RuntimeError("Support inbox exceeded bounded source results")
    previous = (
        (window.before.received_at, window.before.case_id.int)
        if window.before is not None
        else None
    )
    for row in rows:
        receipt = row.receipt
        key = receipt.received_at, receipt.case_id.int
        if receipt.received_at > window.anchor_at or (previous is not None and key >= previous):
            raise RuntimeError("Support inbox violated anchored descending source ordering")
        if (
            (filters.case_id is not None and receipt.case_id != filters.case_id)
            or (filters.actor_id is not None and row.actor_id != filters.actor_id)
            or (filters.topic is not None and row.topic != filters.topic)
            or (filters.status is not None and receipt.status != filters.status)
            or (filters.anonymous is not None and (row.actor_id is None) != filters.anonymous)
            or (filters.received_from is not None and receipt.received_at < filters.received_from)
            or (
                filters.received_before is not None
                and receipt.received_at >= filters.received_before
            )
        ):
            raise RuntimeError("Support inbox returned a source outside the actual filters")
        previous = key


@dataclass(frozen=True, slots=True)
class SearchOperatorSupportCases:
    unit_of_work: OperatorSupportInboxUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter
    cursor_codec: OperatorSupportInboxCursorCodec

    async def __call__(
        self,
        credential: SessionCredential,
        filters: OperatorSupportFilters,
        cursor: str | None = None,
    ) -> OperatorSupportInboxPage:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            now = await transaction.now()
            digest = await self.fingerprinter.fingerprint(filters.fingerprint_parts())
            scope = OperatorCursorScope(principal.access.account_id, principal.access.version)
            position = (
                self.cursor_codec.decode_inbox(scope, digest, cursor, now)
                if cursor is not None
                else None
            )
            window = OperatorSupportWindow(
                position.anchor_at if position is not None else now, position
            )
            rows = await transaction.search_support_cases(filters, window)
            _validate_inbox(rows, filters, window)
            visible = rows[:OPERATOR_SUPPORT_PAGE_SIZE]
            next_cursor = (
                self.cursor_codec.encode_inbox(
                    scope,
                    digest,
                    OperatorSupportPosition(
                        window.anchor_at,
                        visible[-1].receipt.received_at,
                        visible[-1].receipt.case_id,
                    ),
                )
                if len(rows) > OPERATOR_SUPPORT_PAGE_SIZE
                else None
            )
            await transaction.save_operator_audit(
                OperatorAudit(
                    uuid4(),
                    principal.access,
                    OperatorAction.SEARCH_SUPPORT_CASES,
                    None,
                    tuple(
                        OperatorResourceRef(OperatorResourceKind.SUPPORT_CASE, row.receipt.case_id)
                        for row in visible
                    ),
                    await transaction.now(),
                    OperatorAuditOutcome.SEARCH,
                    digest,
                )
            )
            await finish_operator(transaction, principal)
            return OperatorSupportInboxPage(visible, next_cursor, window.anchor_at)


@dataclass(frozen=True, slots=True)
class ReadOperatorSupportHistory:
    unit_of_work: OperatorSupportInboxUnitOfWork
    hasher: SessionHasher
    cursor_codec: OperatorSupportInboxCursorCodec

    async def __call__(
        self, credential: SessionCredential, case_id: UUID, cursor: str | None = None
    ) -> OperatorSupportHistoryPage | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            scope = OperatorCursorScope(principal.access.account_id, principal.access.version)
            position = (
                self.cursor_codec.decode_history(scope, case_id, cursor)
                if cursor is not None
                else None
            )
            head = await transaction.support_history_head(case_id)
            result = None
            if head is not None:
                if head.case_id != case_id:
                    raise RuntimeError(
                        "Support history head differs from its actual requested case"
                    )
                anchor = position.anchor_version if position is not None else head.version
                if anchor > head.version:
                    raise InvalidOperatorCursorError
                before = position.before_version if position is not None else None
                rows = await transaction.support_history(
                    case_id, OperatorSupportHistoryWindow(anchor, before)
                )
                if len(rows) > OPERATOR_SUPPORT_PAGE_SIZE + 1:
                    raise RuntimeError("Support history exceeded bounded source results")
                previous = before if before is not None else anchor + 1
                for row in rows:
                    source = row.receipt
                    if (
                        source.case_id != case_id
                        or source.received_at != head.received_at
                        or source.version > anchor
                        or source.version >= previous
                    ):
                        raise RuntimeError("Support history lost its actual ordered case revision")
                    previous = source.version
                visible = rows[:OPERATOR_SUPPORT_PAGE_SIZE]
                next_cursor = (
                    self.cursor_codec.encode_history(
                        scope,
                        case_id,
                        OperatorSupportHistoryPosition(anchor, visible[-1].receipt.version),
                    )
                    if len(rows) > OPERATOR_SUPPORT_PAGE_SIZE
                    else None
                )
                result = OperatorSupportHistoryPage(case_id, anchor, visible, next_cursor)
            ref = OperatorResourceRef(OperatorResourceKind.SUPPORT_CASE, case_id)
            await transaction.save_operator_audit(
                OperatorAudit(
                    uuid4(),
                    principal.access,
                    OperatorAction.READ_SUPPORT_CASE,
                    ref,
                    (ref,) if head is not None else (),
                    await transaction.now(),
                    OperatorAuditOutcome.READ
                    if head is not None
                    else OperatorAuditOutcome.NOT_FOUND,
                )
            )
            await finish_operator(transaction, principal)
            return result
