"""Audited account-scoped retained request root search and raw version history."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from studymate.application.idempotency import IntentFingerprinter
from studymate.application.identity.sessions import SessionCredential, SessionHasher
from studymate.application.operator.authority import (
    OperatorPrincipal,
    finish_operator,
    require_operator,
)
from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.operator.request_ports import (
    OperatorRequestCursorCodec,
    OperatorRequestFilters,
    OperatorRequestHistoryPosition,
    OperatorRequestHistoryWindow,
    OperatorRequestPosition,
    OperatorRequestTransaction,
    OperatorRequestUnitOfWork,
)
from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.operator.connection_requests import (
    OPERATOR_REQUEST_ACKS_PER_REVISION,
    OPERATOR_REQUEST_PAGE_SIZE,
    OperatorRequestAcknowledgement,
    OperatorRequestRevision,
    OperatorRequestRoot,
    OperatorRequestSnapshot,
)


@dataclass(frozen=True, slots=True)
class OperatorRequestsPage:
    account_id: UUID
    requests: tuple[OperatorRequestRoot, ...]
    next_cursor: str | None
    anchor_sent_at: datetime | None
    anchor_request_id: UUID | None
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class OperatorRequestHistoryPage:
    snapshot: OperatorRequestSnapshot = field(repr=False)
    revisions: tuple[OperatorRequestRevision, ...] = field(repr=False)
    next_cursor: str | None
    anchor_version: int
    observed_at: datetime
    acknowledgements: tuple[OperatorRequestAcknowledgement, ...]


async def audit_request_account(
    transaction: OperatorRequestTransaction,
    principal: OperatorPrincipal,
    account_id: UUID,
    *,
    found: bool,
) -> None:
    """Request inspections audit their REAL account scope, never a fabricated revision UUID."""
    resource = OperatorResourceRef(OperatorResourceKind.ACCOUNT, account_id)
    await transaction.save_operator_audit(
        OperatorAudit(
            uuid4(),
            principal.access,
            OperatorAction.READ_ACCOUNT,
            resource,
            (resource,) if found else (),
            await transaction.now(),
            OperatorAuditOutcome.READ if found else OperatorAuditOutcome.NOT_FOUND,
        )
    )
    await finish_operator(transaction, principal)


def validate_request_roots(
    rows: tuple[OperatorRequestRoot, ...],
    account_id: UUID,
    filters: OperatorRequestFilters,
    position: OperatorRequestPosition | None,
) -> None:
    if len(rows) > OPERATOR_REQUEST_PAGE_SIZE + 1:
        raise RuntimeError("Request root source exceeded its bounded metadata page")
    previous = (
        (position.before_sent_at, position.before_request_id.int) if position is not None else None
    )
    for row in rows:
        key = row.sent_at, row.id.int
        if (
            not row.includes(account_id)
            or not filters.matches(row, account_id)
            or (previous is not None and key >= previous)
            or (
                position is not None
                and key > (position.anchor_sent_at, position.anchor_request_id.int)
            )
        ):
            raise RuntimeError(
                "Request root source violates actual owner, filter or metadata ordering"
            )
        previous = key


@dataclass(frozen=True, slots=True)
class ReadOperatorRequests:
    unit_of_work: OperatorRequestUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter
    cursor_codec: OperatorRequestCursorCodec

    async def __call__(
        self,
        credential: SessionCredential,
        account_id: UUID,
        filters: OperatorRequestFilters,
        cursor: str | None = None,
    ) -> OperatorRequestsPage | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            actual = await transaction.request_account(account_id)
            if actual is None:
                await audit_request_account(transaction, principal, account_id, found=False)
                return None
            if actual != account_id:
                raise RuntimeError(
                    "Request root account source belongs to another requested account"
                )
            digest = await self.fingerprinter.fingerprint(filters.fingerprint_parts())
            scope = OperatorCursorScope(principal.access.account_id, principal.access.version)
            position = (
                self.cursor_codec.decode_roots(scope, account_id, digest, cursor)
                if cursor is not None
                else None
            )
            rows = await transaction.request_roots(account_id, filters, position)
            validate_request_roots(rows, account_id, filters, position)
            anchor_at, anchor_id = (
                (position.anchor_sent_at, position.anchor_request_id)
                if position is not None
                else (rows[0].sent_at, rows[0].id)
                if rows
                else (None, None)
            )
            visible = rows[:OPERATOR_REQUEST_PAGE_SIZE]
            continuation = None
            if len(rows) > OPERATOR_REQUEST_PAGE_SIZE:
                if anchor_at is None or anchor_id is None:
                    raise RuntimeError("Request root source lost its actual continuation anchor")
                continuation = self.cursor_codec.encode_roots(
                    scope,
                    account_id,
                    digest,
                    OperatorRequestPosition(
                        anchor_at, anchor_id, visible[-1].sent_at, visible[-1].id
                    ),
                )
            observed = await transaction.now()
            await audit_request_account(transaction, principal, account_id, found=True)
            return OperatorRequestsPage(
                account_id, visible, continuation, anchor_at, anchor_id, observed
            )


@dataclass(frozen=True, slots=True)
class ReadOperatorRequestHistory:
    unit_of_work: OperatorRequestUnitOfWork
    hasher: SessionHasher
    cursor_codec: OperatorRequestCursorCodec

    async def __call__(
        self,
        credential: SessionCredential,
        account_id: UUID,
        request_id: UUID,
        cursor: str | None = None,
    ) -> OperatorRequestHistoryPage | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            actual = await transaction.request_account(account_id)
            if actual is None:
                await audit_request_account(transaction, principal, account_id, found=False)
                return None
            if actual != account_id:
                raise RuntimeError(
                    "Request history account source belongs to another requested account"
                )
            head = await transaction.request_history_head(account_id, request_id)
            if head is None:
                # The real parent ACCOUNT was inspected even when its requested child is absent.
                await audit_request_account(transaction, principal, account_id, found=True)
                return None
            if head.snapshot.root.id != request_id or not head.snapshot.root.includes(account_id):
                raise RuntimeError(
                    "Request history head belongs to another actual owner or request"
                )
            scope = OperatorCursorScope(principal.access.account_id, principal.access.version)
            position = (
                self.cursor_codec.decode_history(scope, account_id, request_id, cursor)
                if cursor is not None
                else None
            )
            if position is not None and position.anchor_version > head.latest_version:
                raise InvalidOperatorCursorError
            anchor = position.anchor_version if position is not None else head.latest_version
            window = OperatorRequestHistoryWindow(
                anchor, position.before_version if position is not None else None
            )
            rows = await transaction.request_revisions(account_id, request_id, window)
            validate_request_revisions(rows, request_id, window)
            visible = rows[:OPERATOR_REQUEST_PAGE_SIZE]
            continuation = (
                self.cursor_codec.encode_history(
                    scope,
                    account_id,
                    request_id,
                    OperatorRequestHistoryPosition(anchor, visible[-1].version),
                )
                if len(rows) > OPERATOR_REQUEST_PAGE_SIZE
                else None
            )
            acknowledgements = await transaction.request_page_acknowledgements(
                account_id, request_id, tuple(row.version for row in visible)
            )
            validate_request_acknowledgements(acknowledgements, head.snapshot.root, visible)
            observed = await transaction.now()
            await audit_request_account(transaction, principal, account_id, found=True)
            return OperatorRequestHistoryPage(
                head.snapshot, visible, continuation, anchor, observed, acknowledgements
            )


def validate_request_revisions(
    rows: tuple[OperatorRequestRevision, ...],
    request_id: UUID,
    window: OperatorRequestHistoryWindow,
) -> None:
    if len(rows) > OPERATOR_REQUEST_PAGE_SIZE + 1:
        raise RuntimeError("Request revision source exceeded its bounded history page")
    previous = (
        window.before_version if window.before_version is not None else window.anchor_version + 1
    )
    for row in rows:
        if (
            row.request_id != request_id
            or row.version > window.anchor_version
            or row.version >= previous
        ):
            raise RuntimeError(
                "Request history source violates actual owner, request or version ordering"
            )
        previous = row.version


def validate_request_acknowledgements(
    rows: tuple[OperatorRequestAcknowledgement, ...],
    root: OperatorRequestRoot,
    revisions: tuple[OperatorRequestRevision, ...],
) -> None:
    visible = {row.version for row in revisions}
    if (
        len(rows) > len(visible) * OPERATOR_REQUEST_ACKS_PER_REVISION
        or len({row.id for row in rows}) != len(rows)
        or len({(row.viewer_id, row.stored_version) for row in rows}) != len(rows)
        or any(
            row.request_id != root.id
            or row.stored_version not in visible
            or row.viewer_id not in (root.sender_id, root.recipient_id)
            for row in rows
        )
    ):
        raise RuntimeError(
            "Request ACK source exceeds its actual visible revision/participant scope"
        )
