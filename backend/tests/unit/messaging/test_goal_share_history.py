from dataclasses import replace
from uuid import UUID, uuid4

import pytest

from studymate.application.messaging.goal_shares import GOAL_SHARE_PAGE_SIZE, ReadGoalShares
from studymate.application.profiles.goals import SavedGoal
from studymate.infrastructure.messaging.goal_share_cursors import FernetGoalShareCursorCodec
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.identity_store import CREDENTIAL
from tests.unit.messaging.test_goal_shares import GoalStore, share


def read(store: GoalStore) -> ReadGoalShares:
    return ReadGoalShares(
        store, Sha256SessionHasher(), FernetGoalShareCursorCodec.from_key(b"x" * 32)
    )


async def test_initial_context_is_real_accepted_baseline_not_a_fake_persisted_share() -> None:
    store = GoalStore()
    baseline = store.memory.baseline
    source = baseline.context.sender_goal
    assert source is not None
    store.memory.goals[store.actor.session.account_id] = SavedGoal(
        source.goal, source.subject_label
    )
    result = await read(store)(CREDENTIAL, store.memory.access.conversation.id)
    assert result.current_context_version == 0
    assert result.anchor_version == 0
    assert result.latest is None
    assert result.history == ()
    assert result.next_cursor is None
    assert result.baseline.baseline == baseline
    assert result.baseline.sender_goal_can_complete
    assert not result.baseline.recipient_goal_can_complete
    assert not store.memory.shares
    assert not store.memory.share_intents


async def test_only_current_owned_exact_goal_version_gets_completion_action() -> None:
    first = GoalStore()
    other = GoalStore(first.memory, UUID(int=3))
    original = await share(first)(first.command())
    peer = await share(other)(other.command(original.context_version))
    result = await read(first)(CREDENTIAL, original.conversation_id)
    assert result.history[0].can_complete
    assert not result.history[1].can_complete
    assert result.latest is not None
    assert result.latest.share == peer
    assert not result.latest.can_complete
    own = first.memory.goals[first.actor.session.account_id]
    assert own is not None
    first.memory.goals[first.actor.session.account_id] = replace(
        own, goal=own.goal.complete(own.goal.updated_at)
    )
    historical = await read(first)(CREDENTIAL, original.conversation_id)
    assert not any(row.can_complete for row in historical.history)
    assert historical.history[0].share.goal == original.goal
    assert original.goal.active  # Original snapshot was active when explicitly shared.
    assert first.access is not None
    first.access = replace(first.access, blocked=True, peer_deleted=True)
    retained = await read(first)(CREDENTIAL, original.conversation_id)
    assert retained.history == historical.history


async def test_bounded_context_history_uses_own_anchor_without_advancing_message_sequence() -> None:
    first = GoalStore()
    second = GoalStore(first.memory, UUID(int=3))
    for version in range(GOAL_SHARE_PAGE_SIZE + 1):
        owner = first if version % 2 == 0 else second
        await share(owner)(owner.command(version))
    conversation_id = first.memory.access.conversation.id
    latest = await read(first)(CREDENTIAL, conversation_id)
    assert len(latest.history) == GOAL_SHARE_PAGE_SIZE
    assert latest.history[0].share.context_version < latest.history[-1].share.context_version
    assert latest.next_cursor is not None
    added = await share(second)(second.command(latest.current_context_version))
    older = await read(first)(CREDENTIAL, conversation_id, latest.next_cursor)
    assert [row.share.context_version for row in older.history] == [1]
    assert older.anchor_version == latest.anchor_version
    assert older.current_context_version == added.context_version
    assert older.latest is not None
    assert older.latest.share == added
    assert older.next_cursor is None
    assert first.memory.access.conversation.next_message_sequence == 1


async def test_baseline_must_be_exact_actual_conversation_request_source() -> None:
    store = GoalStore()
    store.memory.baseline = replace(store.memory.baseline, request_id=uuid4())
    with pytest.raises(RuntimeError, match="accepted request"):
        await read(store)(CREDENTIAL, store.memory.access.conversation.id)
