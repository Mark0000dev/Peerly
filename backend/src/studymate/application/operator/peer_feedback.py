"""Three explicit privileged retained-feedback reads, never moderation or student policy."""

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
from studymate.application.operator.feedback_ports import (
    OperatorFeedbackCursorCodec,
    OperatorFeedbackFilters,
    OperatorFeedbackHistoryPosition,
    OperatorFeedbackHistoryWindow,
    OperatorFeedbackTimePosition,
    OperatorFeedbackTransaction,
    OperatorFeedbackUnitOfWork,
)
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.operator.peer_feedback import (
    OPERATOR_FEEDBACK_PAGE_SIZE,
    OperatorFeedbackRemoval,
    OperatorFeedbackRevision,
    OperatorFeedbackRoot,
)


@dataclass(frozen=True, slots=True)
class OperatorFeedbackRootsPage:
    account_id: UUID
    feedback: tuple[OperatorFeedbackRoot, ...]
    next_cursor: str | None
    anchor_changed_at: datetime | None
    anchor_feedback_id: UUID | None
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class OperatorFeedbackHistoryPage:
    root: OperatorFeedbackRoot
    revisions: tuple[OperatorFeedbackRevision, ...] = field(repr=False)
    next_cursor: str | None
    anchor_version: int
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class OperatorFeedbackRemovalsPage:
    root: OperatorFeedbackRoot
    removals: tuple[OperatorFeedbackRemoval, ...] = field(repr=False)
    next_cursor: str | None
    anchor_removed_at: datetime | None
    anchor_removal_id: UUID | None
    observed_at: datetime


async def audit_feedback_account(
    transaction: OperatorAuditTransaction,
    principal: OperatorPrincipal,
    account_id: UUID,
    *,
    found: bool,
) -> None:
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


async def feedback_principal(
    transaction: OperatorFeedbackTransaction,
    credential: SessionCredential,
    hasher: SessionHasher,
    account_id: UUID,
) -> OperatorPrincipal | None:
    principal = await require_operator(transaction, credential, hasher)
    actual = await transaction.feedback_account(account_id)
    if actual is None:
        await audit_feedback_account(transaction, principal, account_id, found=False)
        return None
    if actual != account_id:
        raise RuntimeError("Feedback account source belongs to another account")
    return principal


async def feedback_child(
    transaction: OperatorFeedbackTransaction,
    principal: OperatorPrincipal,
    account_id: UUID,
    feedback_id: UUID,
) -> OperatorFeedbackRoot | None:
    root = await transaction.feedback_root(account_id, feedback_id)
    if root is None:
        await audit_feedback_account(transaction, principal, account_id, found=True)
        return None
    if root.id != feedback_id or not root.includes(account_id):
        raise RuntimeError("Feedback root belongs to another actual participant or feedback")
    return root


def validate_feedback_roots(
    rows: tuple[OperatorFeedbackRoot, ...],
    account_id: UUID,
    filters: OperatorFeedbackFilters,
    position: OperatorFeedbackTimePosition | None,
) -> None:
    if len(rows) > OPERATOR_FEEDBACK_PAGE_SIZE + 1:
        raise RuntimeError("Feedback source exceeded its bounded metadata page")
    previous = (position.before_at, position.before_id.int) if position is not None else None
    for row in rows:
        key = row.current_changed_at, row.id.int
        if (
            not filters.matches(row, account_id)
            or (previous is not None and key >= previous)
            or (position is not None and key > (position.anchor_at, position.anchor_id.int))
        ):
            raise RuntimeError(
                "Feedback metadata violates participant/filter/current-pointer ordering"
            )
        previous = key


def validate_feedback_revisions(
    rows: tuple[OperatorFeedbackRevision, ...],
    root: OperatorFeedbackRoot,
    window: OperatorFeedbackHistoryWindow,
) -> None:
    if len(rows) > OPERATOR_FEEDBACK_PAGE_SIZE + 1:
        raise RuntimeError("Feedback source exceeded its bounded revision page")
    before = (
        window.before_version if window.before_version is not None else window.anchor_version + 1
    )
    for row in rows:
        if (
            (
                row.feedback_id,
                row.conversation_id,
                row.reviewer_id,
                row.partner_id,
                row.low_id,
                row.high_id,
            )
            != (
                root.id,
                root.conversation_id,
                root.reviewer_id,
                root.partner_id,
                root.low_id,
                root.high_id,
            )
            or row.version > window.anchor_version
            or row.version >= before
        ):
            raise RuntimeError("Feedback revision violates its actual participant/version scope")
        before = row.version


def validate_feedback_removals(
    rows: tuple[OperatorFeedbackRemoval, ...],
    feedback_id: UUID,
    position: OperatorFeedbackTimePosition | None,
) -> None:
    if len(rows) > OPERATOR_FEEDBACK_PAGE_SIZE + 1:
        raise RuntimeError("Feedback source exceeded its bounded removal page")
    previous = (position.before_at, position.before_id.int) if position is not None else None
    for row in rows:
        key = row.removed_at, row.id.int
        if (
            row.feedback_id != feedback_id
            or (previous is not None and key >= previous)
            or (position is not None and key > (position.anchor_at, position.anchor_id.int))
        ):
            raise RuntimeError("Feedback removal violates its actual source/metadata ordering")
        previous = key


@dataclass(frozen=True, slots=True)
class ReadOperatorFeedback:
    unit_of_work: OperatorFeedbackUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter
    cursor_codec: OperatorFeedbackCursorCodec

    async def __call__(
        self,
        credential: SessionCredential,
        account_id: UUID,
        filters: OperatorFeedbackFilters,
        cursor: str | None = None,
    ) -> OperatorFeedbackRootsPage | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await feedback_principal(transaction, credential, self.hasher, account_id)
            if principal is None:
                return None
            digest = await self.fingerprinter.fingerprint(filters.fingerprint_parts())
            scope = OperatorCursorScope(principal.access.account_id, principal.access.version)
            position = (
                self.cursor_codec.decode_roots(scope, account_id, digest, cursor)
                if cursor is not None
                else None
            )
            rows = await transaction.feedback_roots(account_id, filters, position)
            validate_feedback_roots(rows, account_id, filters, position)
            anchor_at, anchor_id = (
                (position.anchor_at, position.anchor_id)
                if position is not None
                else (rows[0].current_changed_at, rows[0].id)
                if rows
                else (None, None)
            )
            visible = rows[:OPERATOR_FEEDBACK_PAGE_SIZE]
            continuation = None
            if len(rows) > OPERATOR_FEEDBACK_PAGE_SIZE:
                if anchor_at is None or anchor_id is None:
                    raise RuntimeError("Feedback metadata lost its actual continuation anchor")
                continuation = self.cursor_codec.encode_roots(
                    scope,
                    account_id,
                    digest,
                    OperatorFeedbackTimePosition(
                        anchor_at, anchor_id, visible[-1].current_changed_at, visible[-1].id
                    ),
                )
            observed = await transaction.now()
            await audit_feedback_account(transaction, principal, account_id, found=True)
            return OperatorFeedbackRootsPage(
                account_id, visible, continuation, anchor_at, anchor_id, observed
            )


@dataclass(frozen=True, slots=True)
class ReadOperatorFeedbackHistory:
    unit_of_work: OperatorFeedbackUnitOfWork
    hasher: SessionHasher
    cursor_codec: OperatorFeedbackCursorCodec

    async def __call__(
        self,
        credential: SessionCredential,
        account_id: UUID,
        feedback_id: UUID,
        cursor: str | None = None,
    ) -> OperatorFeedbackHistoryPage | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await feedback_principal(transaction, credential, self.hasher, account_id)
            if principal is None:
                return None
            head = await transaction.feedback_history_head(account_id, feedback_id)
            if head is None:
                await audit_feedback_account(transaction, principal, account_id, found=True)
                return None
            root = head.root
            if root.id != feedback_id or not root.includes(account_id):
                raise RuntimeError("Feedback history head belongs to another actual participant")
            scope = OperatorCursorScope(principal.access.account_id, principal.access.version)
            position = (
                self.cursor_codec.decode_history(scope, account_id, feedback_id, cursor)
                if cursor is not None
                else None
            )
            if position is not None and position.anchor_version > head.latest_version:
                raise InvalidOperatorCursorError
            anchor = position.anchor_version if position is not None else head.latest_version
            window = OperatorFeedbackHistoryWindow(
                anchor, position.before_version if position is not None else None
            )
            rows = await transaction.feedback_revisions(account_id, feedback_id, window)
            validate_feedback_revisions(rows, root, window)
            visible = rows[:OPERATOR_FEEDBACK_PAGE_SIZE]
            continuation = (
                self.cursor_codec.encode_history(
                    scope,
                    account_id,
                    feedback_id,
                    OperatorFeedbackHistoryPosition(anchor, visible[-1].version),
                )
                if len(rows) > OPERATOR_FEEDBACK_PAGE_SIZE
                else None
            )
            observed = await transaction.now()
            await audit_feedback_account(transaction, principal, account_id, found=True)
            return OperatorFeedbackHistoryPage(root, visible, continuation, anchor, observed)


@dataclass(frozen=True, slots=True)
class ReadOperatorFeedbackRemovals:
    unit_of_work: OperatorFeedbackUnitOfWork
    hasher: SessionHasher
    cursor_codec: OperatorFeedbackCursorCodec

    async def __call__(
        self,
        credential: SessionCredential,
        account_id: UUID,
        feedback_id: UUID,
        cursor: str | None = None,
    ) -> OperatorFeedbackRemovalsPage | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await feedback_principal(transaction, credential, self.hasher, account_id)
            if principal is None:
                return None
            root = await feedback_child(transaction, principal, account_id, feedback_id)
            if root is None:
                return None
            scope = OperatorCursorScope(principal.access.account_id, principal.access.version)
            position = (
                self.cursor_codec.decode_removals(scope, account_id, feedback_id, cursor)
                if cursor is not None
                else None
            )
            rows = await transaction.feedback_removals(account_id, feedback_id, position)
            validate_feedback_removals(rows, feedback_id, position)
            anchor_at, anchor_id = (
                (position.anchor_at, position.anchor_id)
                if position is not None
                else (rows[0].removed_at, rows[0].id)
                if rows
                else (None, None)
            )
            visible = rows[:OPERATOR_FEEDBACK_PAGE_SIZE]
            continuation = None
            if len(rows) > OPERATOR_FEEDBACK_PAGE_SIZE:
                if anchor_at is None or anchor_id is None:
                    raise RuntimeError("Feedback removals lost its actual continuation anchor")
                continuation = self.cursor_codec.encode_removals(
                    scope,
                    account_id,
                    feedback_id,
                    OperatorFeedbackTimePosition(
                        anchor_at, anchor_id, visible[-1].removed_at, visible[-1].id
                    ),
                )
            observed = await transaction.now()
            await audit_feedback_account(transaction, principal, account_id, found=True)
            return OperatorFeedbackRemovalsPage(
                root, visible, continuation, anchor_at, anchor_id, observed
            )
