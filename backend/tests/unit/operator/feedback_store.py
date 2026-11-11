from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID, uuid4

from studymate.application.operator.feedback_ports import (
    OperatorFeedbackFilters,
    OperatorFeedbackHistoryHead,
    OperatorFeedbackHistoryWindow,
    OperatorFeedbackTimePosition,
)
from studymate.domain.operator.peer_feedback import (
    OPERATOR_FEEDBACK_PAGE_SIZE,
    OperatorFeedbackRemoval,
    OperatorFeedbackRevision,
    OperatorFeedbackRoot,
)
from studymate.domain.operator.timeline import OperatorEventOrigin
from tests.unit.identity_store import NOW
from tests.unit.operator.store import TARGET, Store

FEEDBACK = UUID(int=7001)
PEER = UUID(int=7002)
CONVERSATION = UUID(int=7003)
RAW_NOTE = "  Private original retained team note\n with spacing  "
RAW_REASON = "  Private raw moderation explanation\n  unchanged "


def root(
    feedback_id: UUID = FEEDBACK, *, received: bool = False, peer: UUID = PEER
) -> OperatorFeedbackRoot:
    return OperatorFeedbackRoot(
        feedback_id,
        peer if received else TARGET,
        TARGET if received else peer,
        CONVERSATION,
        TARGET,
        peer,
        1,
        None,
        NOW,
    )


def revision(version: int = 1, feedback_id: UUID = FEEDBACK) -> OperatorFeedbackRevision:
    return OperatorFeedbackRevision(
        feedback_id,
        version,
        CONVERSATION,
        TARGET,
        PEER,
        TARGET,
        PEER,
        UUID(int=7004),
        "yes",
        UUID(int=7005),
        UUID(int=7006),
        "maybe",
        ("supportive", "easy_to_communicate"),
        RAW_NOTE,
        NOW - timedelta(seconds=version),
        OperatorEventOrigin(),
    )


def removal(index: int = 1, feedback_id: UUID = FEEDBACK) -> OperatorFeedbackRemoval:
    return OperatorFeedbackRemoval(
        UUID(int=8000 + index),
        feedback_id,
        1,
        uuid4(),
        1,
        True,
        "fraudulent",
        RAW_REASON,
        NOW + timedelta(seconds=index),
        OperatorEventOrigin(),
    )


class FeedbackStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.accounts = {TARGET, PEER}
        self.roots = {FEEDBACK: root()}
        self.revisions: dict[UUID, tuple[OperatorFeedbackRevision, ...]] = {FEEDBACK: (revision(),)}
        self.removals: tuple[OperatorFeedbackRemoval, ...] = ()
        self.account_override: UUID | None = None
        self.root_override: OperatorFeedbackRoot | None = None
        self.root_rows: tuple[OperatorFeedbackRoot, ...] | None = None
        self.revision_rows: tuple[OperatorFeedbackRevision, ...] | None = None
        self.removal_rows: tuple[OperatorFeedbackRemoval, ...] | None = None
        self.head_override: OperatorFeedbackHistoryHead | None = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["FeedbackStore"]:
        async with Store.transaction(self):
            yield self

    async def feedback_account(self, account_id: UUID) -> UUID | None:
        self.queried()
        return self.account_override or (account_id if account_id in self.accounts else None)

    async def feedback_root(
        self, account_id: UUID, feedback_id: UUID
    ) -> OperatorFeedbackRoot | None:
        self.queried()
        if self.root_override is not None:
            return self.root_override
        row = self.roots.get(feedback_id)
        return row if row is not None and row.includes(account_id) else None

    async def feedback_roots(
        self,
        account_id: UUID,
        filters: OperatorFeedbackFilters,
        position: OperatorFeedbackTimePosition | None,
    ) -> tuple[OperatorFeedbackRoot, ...]:
        self.queried()
        if self.root_rows is not None:
            return self.root_rows
        rows = (
            row
            for row in self.roots.values()
            if filters.matches(row, account_id)
            and (
                position is None
                or (
                    (row.current_changed_at, row.id.int)
                    <= (position.anchor_at, position.anchor_id.int)
                    and (row.current_changed_at, row.id.int)
                    < (position.before_at, position.before_id.int)
                )
            )
        )
        return tuple(
            sorted(rows, key=lambda row: (row.current_changed_at, row.id.int), reverse=True)
        )[: OPERATOR_FEEDBACK_PAGE_SIZE + 1]

    async def feedback_history_head(
        self, account_id: UUID, feedback_id: UUID
    ) -> OperatorFeedbackHistoryHead | None:
        if self.head_override is not None:
            return self.head_override
        source = await self.feedback_root(account_id, feedback_id)
        return (
            OperatorFeedbackHistoryHead(
                source, max(row.version for row in self.revisions[feedback_id])
            )
            if source is not None
            else None
        )

    async def feedback_revisions(
        self, account_id: UUID, feedback_id: UUID, window: OperatorFeedbackHistoryWindow
    ) -> tuple[OperatorFeedbackRevision, ...]:
        self.queried()
        assert self.roots[feedback_id].includes(account_id)
        if self.revision_rows is not None:
            return self.revision_rows
        return tuple(
            sorted(
                (
                    row
                    for row in self.revisions[feedback_id]
                    if row.version <= window.anchor_version
                    and (window.before_version is None or row.version < window.before_version)
                ),
                key=lambda row: row.version,
                reverse=True,
            )
        )[: OPERATOR_FEEDBACK_PAGE_SIZE + 1]

    async def feedback_removals(
        self, account_id: UUID, feedback_id: UUID, position: OperatorFeedbackTimePosition | None
    ) -> tuple[OperatorFeedbackRemoval, ...]:
        self.queried()
        assert self.roots[feedback_id].includes(account_id)
        if self.removal_rows is not None:
            return self.removal_rows
        return tuple(
            sorted(
                (
                    row
                    for row in self.removals
                    if row.feedback_id == feedback_id
                    and (
                        position is None
                        or (
                            (row.removed_at, row.id.int)
                            <= (position.anchor_at, position.anchor_id.int)
                            and (row.removed_at, row.id.int)
                            < (position.before_at, position.before_id.int)
                        )
                    )
                ),
                key=lambda row: (row.removed_at, row.id.int),
                reverse=True,
            )
        )[: OPERATOR_FEEDBACK_PAGE_SIZE + 1]
