"""Audited account-scoped retained goal root search and raw version history."""

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
from studymate.application.operator.goal_ports import (
    OperatorGoalCursorCodec,
    OperatorGoalFilters,
    OperatorGoalHistoryPosition,
    OperatorGoalHistoryWindow,
    OperatorGoalRootPosition,
    OperatorGoalTransaction,
    OperatorGoalUnitOfWork,
)
from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.operator.goals import (
    OPERATOR_GOAL_PAGE_SIZE,
    OperatorGoalRevision,
    OperatorGoalRoot,
)


@dataclass(frozen=True, slots=True)
class OperatorGoalsPage:
    account_id: UUID
    goals: tuple[OperatorGoalRoot, ...]
    next_cursor: str | None
    anchor_created_at: datetime | None
    anchor_goal_id: UUID | None
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class OperatorGoalHistoryPage:
    goal: OperatorGoalRoot
    revisions: tuple[OperatorGoalRevision, ...] = field(repr=False)
    next_cursor: str | None
    anchor_version: int
    observed_at: datetime


async def audit_goal_account(
    transaction: OperatorGoalTransaction,
    principal: OperatorPrincipal,
    account_id: UUID,
    *,
    found: bool,
) -> None:
    """Goal inspections audit their REAL account scope, never a fabricated revision UUID."""
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


def validate_goal_roots(
    rows: tuple[OperatorGoalRoot, ...],
    account_id: UUID,
    filters: OperatorGoalFilters,
    position: OperatorGoalRootPosition | None,
) -> None:
    if len(rows) > OPERATOR_GOAL_PAGE_SIZE + 1:
        raise RuntimeError("Goal root source exceeded its bounded metadata page")
    previous = (
        (position.before_created_at, position.before_goal_id.int) if position is not None else None
    )
    for row in rows:
        key = row.created_at, row.id.int
        if (
            row.account_id != account_id
            or not filters.matches(row)
            or (previous is not None and key >= previous)
            or (
                position is not None
                and key > (position.anchor_created_at, position.anchor_goal_id.int)
            )
        ):
            raise RuntimeError(
                "Goal root source violates actual owner, filter or metadata ordering"
            )
        previous = key


@dataclass(frozen=True, slots=True)
class ReadOperatorGoals:
    unit_of_work: OperatorGoalUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter
    cursor_codec: OperatorGoalCursorCodec

    async def __call__(
        self,
        credential: SessionCredential,
        account_id: UUID,
        filters: OperatorGoalFilters,
        cursor: str | None = None,
    ) -> OperatorGoalsPage | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            actual = await transaction.goal_account(account_id)
            if actual is None:
                await audit_goal_account(transaction, principal, account_id, found=False)
                return None
            if actual != account_id:
                raise RuntimeError("Goal root account source belongs to another requested account")
            digest = await self.fingerprinter.fingerprint(filters.fingerprint_parts())
            scope = OperatorCursorScope(principal.access.account_id, principal.access.version)
            position = (
                self.cursor_codec.decode_roots(scope, account_id, digest, cursor)
                if cursor is not None
                else None
            )
            rows = await transaction.goal_roots(account_id, filters, position)
            validate_goal_roots(rows, account_id, filters, position)
            anchor_at, anchor_id = (
                (position.anchor_created_at, position.anchor_goal_id)
                if position is not None
                else (rows[0].created_at, rows[0].id)
                if rows
                else (None, None)
            )
            visible = rows[:OPERATOR_GOAL_PAGE_SIZE]
            continuation = None
            if len(rows) > OPERATOR_GOAL_PAGE_SIZE:
                if anchor_at is None or anchor_id is None:
                    raise RuntimeError("Goal root source lost its actual continuation anchor")
                continuation = self.cursor_codec.encode_roots(
                    scope,
                    account_id,
                    digest,
                    OperatorGoalRootPosition(
                        anchor_at, anchor_id, visible[-1].created_at, visible[-1].id
                    ),
                )
            observed = await transaction.now()
            await audit_goal_account(transaction, principal, account_id, found=True)
            return OperatorGoalsPage(
                account_id, visible, continuation, anchor_at, anchor_id, observed
            )


@dataclass(frozen=True, slots=True)
class ReadOperatorGoalHistory:
    unit_of_work: OperatorGoalUnitOfWork
    hasher: SessionHasher
    cursor_codec: OperatorGoalCursorCodec

    async def __call__(
        self,
        credential: SessionCredential,
        account_id: UUID,
        goal_id: UUID,
        cursor: str | None = None,
    ) -> OperatorGoalHistoryPage | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            actual = await transaction.goal_account(account_id)
            if actual is None:
                await audit_goal_account(transaction, principal, account_id, found=False)
                return None
            if actual != account_id:
                raise RuntimeError(
                    "Goal history account source belongs to another requested account"
                )
            head = await transaction.goal_history_head(account_id, goal_id)
            if head is None:
                # The real parent ACCOUNT was inspected even when its requested child is absent.
                await audit_goal_account(transaction, principal, account_id, found=True)
                return None
            if head.goal.id != goal_id or head.goal.account_id != account_id:
                raise RuntimeError("Goal history head belongs to another actual owner or goal")
            scope = OperatorCursorScope(principal.access.account_id, principal.access.version)
            position = (
                self.cursor_codec.decode_history(scope, account_id, goal_id, cursor)
                if cursor is not None
                else None
            )
            if position is not None and position.anchor_version > head.latest_version:
                raise InvalidOperatorCursorError
            anchor = position.anchor_version if position is not None else head.latest_version
            window = OperatorGoalHistoryWindow(
                anchor, position.before_version if position is not None else None
            )
            rows = await transaction.goal_history_revisions(account_id, goal_id, window)
            validate_goal_revisions(rows, account_id, goal_id, window)
            visible = rows[:OPERATOR_GOAL_PAGE_SIZE]
            continuation = (
                self.cursor_codec.encode_history(
                    scope,
                    account_id,
                    goal_id,
                    OperatorGoalHistoryPosition(anchor, visible[-1].version),
                )
                if len(rows) > OPERATOR_GOAL_PAGE_SIZE
                else None
            )
            observed = await transaction.now()
            await audit_goal_account(transaction, principal, account_id, found=True)
            return OperatorGoalHistoryPage(head.goal, visible, continuation, anchor, observed)


def validate_goal_revisions(
    rows: tuple[OperatorGoalRevision, ...],
    account_id: UUID,
    goal_id: UUID,
    window: OperatorGoalHistoryWindow,
) -> None:
    if len(rows) > OPERATOR_GOAL_PAGE_SIZE + 1:
        raise RuntimeError("Goal revision source exceeded its bounded history page")
    previous = (
        window.before_version if window.before_version is not None else window.anchor_version + 1
    )
    for row in rows:
        if (
            row.account_id != account_id
            or row.goal_id != goal_id
            or row.version > window.anchor_version
            or row.version >= previous
        ):
            raise RuntimeError(
                "Goal history source violates actual owner, goal or version ordering"
            )
        previous = row.version
