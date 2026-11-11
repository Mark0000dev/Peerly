from dataclasses import replace
from uuid import UUID, uuid4

import pytest

from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.messaging.goal_shares import (
    GOAL_SHARE_PAGE_SIZE,
    GoalShareCursor,
    GoalShareIntent,
    GoalShareWindow,
    InvalidGoalShareCursorError,
)
from studymate.application.profiles.goals import SavedGoal
from studymate.domain.goal_shares import GoalShare
from studymate.infrastructure.messaging.goal_share_cursors import FernetGoalShareCursorCodec
from tests.unit.identity_store import CREDENTIAL
from tests.unit.messaging.test_goal_share_history import read
from tests.unit.messaging.test_goal_shares import GoalStore, share


class BoundaryStore(GoalStore):
    def __init__(self) -> None:
        super().__init__()
        self.forced_rows: tuple[GoalShare, ...] | None = None
        self.expire_after_intent = False
        self.expire_after_goal = False

    async def goal_share_intent(self, actor_id: UUID, key: IntentKey) -> GoalShareIntent | None:
        value = await super().goal_share_intent(actor_id, key)
        if self.expire_after_intent:
            self.clock = self.actor.session.expires_at
        return value

    async def active_goal(self, account_id: UUID) -> SavedGoal | None:
        value = await super().active_goal(account_id)
        if self.expire_after_goal:
            self.clock = self.actor.session.expires_at
        return value

    async def goal_share_history(
        self, actor_id: UUID, conversation_id: UUID, window: GoalShareWindow
    ) -> tuple[GoalShare, ...]:
        return (
            self.forced_rows
            if self.forced_rows is not None
            else await super().goal_share_history(actor_id, conversation_id, window)
        )


async def test_original_receipt_cannot_bypass_live_session_or_owned_source_scope() -> None:
    store = BoundaryStore()
    command = store.command()
    result = await share(store)(command)
    store.expire_after_intent = True
    with pytest.raises(UnauthenticatedError):
        await share(store)(command)
    store.expire_after_intent = False
    store.clock = result.shared_at
    intent = store.memory.share_intents[store.actor.session.account_id, command.intent_key]
    store.memory.share_intents[store.actor.session.account_id, command.intent_key] = replace(
        intent, result=replace(result, conversation_id=uuid4())
    )
    with pytest.raises(RuntimeError, match="owned source"):
        await share(store)(command)


async def test_foreign_active_goal_source_cannot_be_published_or_grant_completion() -> None:
    store = BoundaryStore()
    command = store.command()
    own = store.memory.goals[store.actor.session.account_id]
    assert own is not None
    store.memory.goals[store.actor.session.account_id] = replace(
        own, goal=replace(own.goal, account_id=UUID(int=3))
    )
    with pytest.raises(RuntimeError, match="another actor"):
        await share(store)(command)
    with pytest.raises(RuntimeError, match="another actor"):
        await read(store)(CREDENTIAL, command.conversation_id)
    assert not store.memory.shares


async def test_latest_context_cannot_point_to_another_conversation() -> None:
    store = BoundaryStore()
    original = await share(store)(store.command())
    store.memory.shares[-1] = replace(original, conversation_id=uuid4())
    with pytest.raises(RuntimeError, match="another conversation"):
        await share(store)(store.command(original.context_version))
    with pytest.raises(RuntimeError, match="another conversation"):
        await read(store)(CREDENTIAL, original.conversation_id)


@pytest.mark.parametrize("violation", ["foreign", "unordered", "unbounded"])
async def test_history_rejects_foreign_or_unbounded_source_rows(violation: str) -> None:
    store = BoundaryStore()
    source = await share(store)(store.command())
    if violation == "foreign":
        store.forced_rows = (replace(source, conversation_id=uuid4()),)
    elif violation == "unordered":
        store.forced_rows = (source, source)
    else:
        store.forced_rows = (source,) * (GOAL_SHARE_PAGE_SIZE + 2)
    with pytest.raises(RuntimeError, match=r"ordering|bounded"):
        await read(store)(CREDENTIAL, source.conversation_id)


async def test_history_rechecks_session_and_refuses_future_context_anchor() -> None:
    store = BoundaryStore()
    conversation_id = store.memory.access.conversation.id
    token = FernetGoalShareCursorCodec.from_key(b"x" * 32).encode(
        store.actor.session.account_id, conversation_id, GoalShareCursor(1, 1)
    )
    with pytest.raises(InvalidGoalShareCursorError):
        await read(store)(CREDENTIAL, conversation_id, token)
    store.expire_after_goal = True
    with pytest.raises(UnauthenticatedError):
        await read(store)(CREDENTIAL, conversation_id)
