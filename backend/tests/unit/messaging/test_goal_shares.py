import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime
from uuid import UUID, uuid4

import pytest

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.application.messaging.goal_shares import (
    GOAL_SHARE_PAGE_SIZE,
    AcceptedGoalBaseline,
    GoalShareContextConflictError,
    GoalShareIntent,
    GoalShareTransaction,
    GoalShareWindow,
    ShareCurrentGoal,
    ShareCurrentGoalCommand,
)
from studymate.application.messaging.ports import ConversationAccess, MessageContactUnavailableError
from studymate.application.profiles.goals import GoalVersionConflictError, SavedGoal
from studymate.domain.goal_shares import GoalShare, GoalShareState
from studymate.domain.study_context import CustomSubjectRef, GoalContent, StudyGoal
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.requests.test_states import request
from tests.unit.test_message_commands import Store

SENDER = UUID(int=2)


def saved_goal(owner_id: UUID) -> SavedGoal:
    return SavedGoal(
        StudyGoal(
            uuid4(),
            owner_id,
            1,
            GoalContent(
                CustomSubjectRef("Private custom subject"), "Private topic", "Private context"
            ),
            NOW,
            NOW,
        ),
        "Private custom subject",
    )


@dataclass(slots=True)
class Memory:
    access: ConversationAccess
    goals: dict[UUID, SavedGoal | None]
    baseline: AcceptedGoalBaseline
    shares: list[GoalShare] = field(default_factory=list)
    share_intents: dict[tuple[UUID, IntentKey], GoalShareIntent] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class GoalStore(Store):
    def __init__(self, memory: Memory | None = None, owner_id: UUID = SENDER) -> None:
        super().__init__()
        assert self.access is not None
        pair = self.access.conversation.pair
        self.memory = (
            memory
            if memory is not None
            else Memory(
                self.access,
                {owner: saved_goal(owner) for owner in (pair.low, pair.high)},
                AcceptedGoalBaseline(
                    self.access.conversation.request_id,
                    self.access.conversation.accepted_request_version,
                    request().context,
                ),
            )
        )
        self.access = self.memory.access
        self.actor = replace(self.actor, session=replace(self.actor.session, account_id=owner_id))
        self.expire_on_share = False
        self.fail_on_share = False

    @asynccontextmanager
    async def transaction(self, _conversation_id: UUID) -> AsyncIterator[GoalShareTransaction]:
        async with self.memory.lock:
            before = self.memory.shares.copy(), self.memory.share_intents.copy()
            try:
                yield self
            except BaseException:
                self.memory.shares, self.memory.share_intents = before
                raise

    async def active_goal(self, account_id: UUID) -> SavedGoal | None:
        assert account_id == self.actor.session.account_id
        return self.memory.goals.get(account_id)

    async def goal_version(self, account_id: UUID, goal_id: UUID, version: int) -> SavedGoal | None:
        current = self.memory.goals.get(account_id)
        return (
            current
            if current is not None
            and current.goal.id == goal_id
            and current.goal.version == version
            else None
        )

    async def goal_share_state(self, actor_id: UUID, conversation_id: UUID) -> GoalShareState:
        assert actor_id == self.actor.session.account_id
        assert self.access is not None
        assert conversation_id == self.access.conversation.id
        return GoalShareState(
            len(self.memory.shares), self.memory.shares[-1] if self.memory.shares else None
        )

    async def accepted_goal_baseline(
        self, actor_id: UUID, conversation_id: UUID
    ) -> AcceptedGoalBaseline:
        assert actor_id == self.actor.session.account_id
        assert conversation_id == self.memory.access.conversation.id
        return self.memory.baseline

    async def goal_share_history(
        self, actor_id: UUID, conversation_id: UUID, window: GoalShareWindow
    ) -> tuple[GoalShare, ...]:
        assert actor_id == self.actor.session.account_id
        return tuple(
            share
            for share in reversed(self.memory.shares)
            if share.conversation_id == conversation_id
            and share.context_version <= window.anchor_version
            and (window.before_version is None or share.context_version < window.before_version)
        )[: GOAL_SHARE_PAGE_SIZE + 1]

    async def goal_share_intent(self, actor_id: UUID, key: IntentKey) -> GoalShareIntent | None:
        return self.memory.share_intents.get((actor_id, key))

    async def save_goal_share(self, share: GoalShare) -> None:
        self.memory.shares.append(share)
        if self.fail_on_share:
            raise RuntimeError("Synthetic share transaction failure")

    async def remember_goal_share(
        self, actor_id: UUID, key: IntentKey, intent: GoalShareIntent, at: datetime
    ) -> None:
        assert at == self.clock
        self.memory.share_intents[actor_id, key] = intent
        if self.expire_on_share:
            self.clock = self.actor.session.expires_at

    def command(self, context_version: int = 0) -> ShareCurrentGoalCommand:
        assert self.access is not None
        own = self.memory.goals[self.actor.session.account_id]
        assert own is not None
        return ShareCurrentGoalCommand(
            CREDENTIAL,
            self.access.conversation.id,
            own.goal.id,
            own.goal.version,
            context_version,
            IntentKey(str(uuid4())),
        )


def share(store: GoalStore) -> ShareCurrentGoal:
    return ShareCurrentGoal(store, Sha256SessionHasher(), HmacIntentFingerprinter(b"x" * 32))


async def test_explicit_custom_share_preserves_baseline_and_message_counter() -> None:
    store = GoalStore()
    command = store.command()
    result = await share(store)(command)
    assert result.context_version == 1
    assert result.goal.content.canonical_subject_id is None
    assert result.goal.id == command.goal_id
    assert result.owner_id == store.actor.session.account_id
    assert "Private" not in repr(result)
    assert store.access is not None
    assert store.access.conversation.next_message_sequence == 1
    assert not store.operations
    assert not store.intents


async def test_original_intent_replays_after_goal_completion_and_contact_loss() -> None:
    store = GoalStore()
    command = store.command()
    result = await share(store)(command)
    store.memory.goals[store.actor.session.account_id] = None
    assert store.access is not None
    store.access = replace(store.access, blocked=True, peer_deleted=True)
    assert await share(store)(command) == result
    with pytest.raises(IdempotencyConflictError):
        await share(store)(replace(command, expected_context_version=1))
    assert len(store.memory.shares) == 1


async def test_identical_latest_goal_deduplicates_even_new_key_and_stale_cas_without_event() -> (
    None
):
    store = GoalStore()
    first, second = await asyncio.gather(
        share(store)(store.command()), share(store)(store.command())
    )
    assert first == second
    assert len(store.memory.shares) == 1
    assert len(store.memory.share_intents) == len((first, second))


async def test_other_partners_concurrent_share_conflicts_instead_of_overwriting_context() -> None:
    first = GoalStore()
    second = GoalStore(first.memory, UUID(int=3))
    results = await asyncio.gather(
        share(first)(first.command()), share(second)(second.command()), return_exceptions=True
    )
    assert sum(isinstance(value, GoalShare) for value in results) == 1
    assert sum(isinstance(value, GoalShareContextConflictError) for value in results) == 1
    assert len(first.memory.shares) == 1


async def test_explicit_reshare_after_different_context_is_not_global_goal_version_dedup() -> None:
    first = GoalStore()
    second = GoalStore(first.memory, UUID(int=3))
    original = await share(first)(first.command())
    other = await share(second)(second.command(original.context_version))
    again = await share(first)(first.command(other.context_version))
    assert again.goal == original.goal
    assert again.id != original.id
    assert again.context_version == other.context_version + 1
    assert len(first.memory.shares) == len((original, other, again))


@pytest.mark.parametrize("cause", ["missing", "changed", "completed"])
async def test_new_share_requires_exact_current_owned_active_goal(cause: str) -> None:
    store = GoalStore()
    command = store.command()
    own = store.memory.goals[store.actor.session.account_id]
    assert own is not None
    if cause == "missing":
        changed = None
    elif cause == "completed":
        changed = replace(own, goal=own.goal.complete(NOW))
    else:
        changed = replace(
            own,
            goal=own.goal.revise(GoalContent(CustomSubjectRef("Different current subject")), NOW),
        )
    store.memory.goals[store.actor.session.account_id] = changed
    with pytest.raises(GoalVersionConflictError):
        await share(store)(command)
    assert not store.memory.shares
    assert not store.memory.share_intents


async def test_new_share_denies_contact_loss_and_banned_actor_even_when_source_still_matches() -> (
    None
):
    store = GoalStore()
    assert store.access is not None
    store.access = replace(store.access, blocked=True)
    with pytest.raises(MessageContactUnavailableError):
        await share(store)(store.command())
    store.access = store.memory.access
    store.actor = replace(store.actor, banned=True)
    with pytest.raises(StudentActionDeniedError):
        await share(store)(store.command())


@pytest.mark.parametrize("failure", ["session", "storage"])
async def test_share_and_intent_rollback_together_on_failure(failure: str) -> None:
    store = GoalStore()
    store.expire_on_share = failure == "session"
    store.fail_on_share = failure == "storage"
    expected = UnauthenticatedError if failure == "session" else RuntimeError
    with pytest.raises(expected):
        await share(store)(store.command())
    assert not store.memory.shares
    assert not store.memory.share_intents


@pytest.mark.parametrize(
    ("goal_version", "context_version"), [(True, 0), (0, 0), (1, True), (1, -1)]
)
def test_command_versions_are_actual_integers_not_coerced_client_flags(
    goal_version: int, context_version: int
) -> None:
    with pytest.raises(ValueError, match="Expected"):
        ShareCurrentGoalCommand(
            CREDENTIAL,
            uuid4(),
            uuid4(),
            goal_version,
            context_version,
            IntentKey("synthetic-goal-share"),
        )
