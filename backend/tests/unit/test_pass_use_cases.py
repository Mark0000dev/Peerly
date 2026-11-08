from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime
from uuid import UUID

import pytest

from studymate.application.discovery.passes import (
    ChangePassCommand,
    ChangePrivatePass,
    DiscoveryContextChangedError,
    PassUndoUnavailableError,
    PrivatePassConflictError,
    PrivatePassIntent,
    PrivatePassTransaction,
)
from studymate.application.discovery.profiles import (
    DiscoveryProfileSource,
    DiscoveryProfileUnavailableError,
)
from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.application.profiles.help_subjects import SavedHelpSubjects
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.discovery_context import DiscoveryContext, discovery_context
from studymate.domain.discovery_passes import PrivatePassRevision
from studymate.domain.study_context import (
    CanonicalSubjectRef,
    HelpRevision,
    HelpSubject,
    HelpSubjects,
)
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.identity_store import CREDENTIAL, NOW, IdentityStore
from tests.unit.test_discovery_profiles import TARGET, source


class Store(IdentityStore):
    def __init__(self) -> None:
        super().__init__()
        self.actor = replace(self.actor, activation_complete=True)
        actor_id = self.actor.session.account_id
        own = source(actor_id, self)
        assert own.setup.goal is not None
        saved = own.setup.goal
        goal = replace(
            saved.goal,
            content=replace(saved.goal.content, subject=CanonicalSubjectRef(UUID(int=50))),
        )
        own = replace(own, setup=replace(own.setup, goal=replace(saved, goal=goal)))
        peer = source(TARGET, self)
        help_revision = HelpRevision(TARGET, 1, HelpSubjects((HelpSubject(UUID(int=50)),)), NOW)
        peer = replace(
            peer,
            setup=replace(
                peer.setup, help_subjects=SavedHelpSubjects(help_revision, ("Synthetic subject",))
            ),
        )
        self.sources = {actor_id: own, TARGET: peer}
        self.passes: dict[tuple[DiscoveryContext, UUID], PrivatePassRevision] = {}
        self.intents: dict[IntentKey, PrivatePassIntent] = {}
        self.latest = 0
        self.blocked = False
        self.expire_on_save = False

    @asynccontextmanager
    async def transaction(self, target_id: UUID) -> AsyncIterator[PrivatePassTransaction]:
        assert target_id == TARGET
        previous = (self.passes.copy(), self.intents.copy(), self.latest)
        try:
            yield self
        except BaseException:
            self.passes, self.intents, self.latest = previous
            raise

    async def profile_source(self, account_id: UUID) -> DiscoveryProfileSource | None:
        return self.sources.get(account_id)

    async def pair_blocked(self, actor_id: UUID, target_id: UUID) -> bool:
        assert actor_id == self.actor.session.account_id
        assert target_id == TARGET
        return self.blocked

    async def pass_intent(self, actor_id: UUID, key: IntentKey) -> PrivatePassIntent | None:
        assert actor_id == self.actor.session.account_id
        return self.intents.get(key)

    async def current_pass(
        self, context: DiscoveryContext, target_id: UUID
    ) -> PrivatePassRevision | None:
        return self.passes.get((context, target_id))

    async def latest_decision_sequence(self, actor_id: UUID) -> int:
        assert actor_id == self.actor.session.account_id
        return self.latest

    async def save_pass(self, revision: PrivatePassRevision) -> None:
        self.passes[revision.context, revision.target_id] = revision
        self.latest = revision.decision_sequence
        if self.expire_on_save:
            self.clock = self.actor.session.expires_at

    async def remember_pass_intent(
        self, actor_id: UUID, key: IntentKey, intent: PrivatePassIntent, at: datetime
    ) -> None:
        assert actor_id == self.actor.session.account_id
        assert at == NOW
        self.intents[key] = intent


def command(store: Store) -> ChangePassCommand:
    own = store.sources[store.actor.session.account_id].setup
    assert own.goal is not None
    context = discovery_context(own.account_id, DiscoveryMode.FIND_HELP, own.goal.goal, None)
    assert context is not None
    return ChangePassCommand(
        CREDENTIAL, context.scope, TARGET, True, 0, IntentKey("synthetic-pass-1")
    )


def use_case(store: Store) -> ChangePrivatePass:
    return ChangePrivatePass(store, Sha256SessionHasher(), HmacIntentFingerprinter(b"k" * 32))


async def test_pass_replay_is_original_and_edited_payload_conflicts() -> None:
    store = Store()
    send = command(store)
    first = await use_case(store)(send)
    store.sources.clear()
    assert await use_case(store)(send) == first
    assert store.latest == 1
    with pytest.raises(IdempotencyConflictError):
        await use_case(store)(replace(send, passed=False))


async def test_undo_then_replay_never_reapplies_an_old_pass() -> None:
    store = Store()
    send = command(store)
    first = await use_case(store)(send)
    undo = replace(
        send,
        passed=False,
        expected_version=first.version,
        undo=True,
        intent_key=IntentKey("synthetic-undo-1"),
    )
    reconsidered = await use_case(store)(undo)
    assert not reconsidered.passed
    assert await use_case(store)(send) == first
    assert store.passes[send.context.bind(store.actor.session.account_id), TARGET] == reconsidered
    assert await use_case(store)(undo) == reconsidered


async def test_next_committed_decision_ends_undo_but_explicit_review_can_reconsider() -> None:
    store = Store()
    send = command(store)
    first = await use_case(store)(send)
    store.latest += 1
    undo = replace(
        send,
        passed=False,
        expected_version=first.version,
        undo=True,
        intent_key=IntentKey("synthetic-undo-1"),
    )
    with pytest.raises(PassUndoUnavailableError):
        await use_case(store)(undo)
    result = await use_case(store)(replace(undo, undo=False))
    assert not result.passed


async def test_goal_edit_requires_refresh_and_does_not_change_prior_pass() -> None:
    store = Store()
    send = command(store)
    own = store.sources[store.actor.session.account_id]
    assert own.setup.goal is not None
    saved = own.setup.goal
    edited = saved.goal.revise(replace(saved.goal.content, topic="Changed topic"), NOW)
    store.sources[store.actor.session.account_id] = replace(
        own, setup=replace(own.setup, goal=replace(saved, goal=edited))
    )
    with pytest.raises(DiscoveryContextChangedError):
        await use_case(store)(send)
    assert not store.passes
    assert not store.intents


async def test_hidden_or_blocked_target_cannot_be_newly_passed_but_can_be_reconsidered() -> None:
    store = Store()
    send = command(store)
    first = await use_case(store)(send)
    store.blocked = True
    with pytest.raises(DiscoveryProfileUnavailableError):
        await use_case(store)(
            replace(send, expected_version=first.version, intent_key=IntentKey("synthetic-pass-2"))
        )
    reconsider = replace(
        send,
        passed=False,
        expected_version=first.version,
        intent_key=IntentKey("synthetic-review-1"),
    )
    assert not (await use_case(store)(reconsider)).passed


async def test_stale_version_and_absent_undo_are_truthful() -> None:
    store = Store()
    send = command(store)
    with pytest.raises(PassUndoUnavailableError):
        await use_case(store)(replace(send, passed=False, undo=True))
    first = await use_case(store)(send)
    with pytest.raises(PrivatePassConflictError) as error:
        await use_case(store)(replace(send, intent_key=IntentKey("synthetic-pass-2")))
    assert error.value.current_version == first.version


async def test_expired_session_rolls_back_decision_sequence_and_intent() -> None:
    store = Store()
    store.expire_on_save = True
    with pytest.raises(UnauthenticatedError):
        await use_case(store)(command(store))
    assert not store.passes
    assert not store.intents
    assert store.latest == 0


async def test_foreign_context_and_incomplete_activation_are_denied() -> None:
    store = Store()
    send = command(store)
    foreign = replace(send.context, goal_id=UUID(int=100))
    with pytest.raises(DiscoveryContextChangedError):
        await use_case(store)(replace(send, context=foreign))
    store.actor = replace(store.actor, activation_complete=False)
    with pytest.raises(StudentActionDeniedError):
        await use_case(store)(send)


async def test_stale_candidate_no_longer_relevant_cannot_be_passed_in_current_goal() -> None:
    store = Store()
    peer = store.sources[TARGET]
    store.sources[TARGET] = replace(peer, setup=replace(peer.setup, help_subjects=None))
    with pytest.raises(DiscoveryProfileUnavailableError):
        await use_case(store)(command(store))
    assert not store.passes


async def test_repeated_state_with_new_intent_does_not_invent_another_decision() -> None:
    store = Store()
    send = command(store)
    first = await use_case(store)(send)
    second = replace(send, expected_version=first.version, intent_key=IntentKey("synthetic-pass-2"))
    assert await use_case(store)(second) is first
    assert store.latest == first.decision_sequence


async def test_absent_pass_cannot_be_fabricated_by_reconsideration() -> None:
    store = Store()
    with pytest.raises(DiscoveryProfileUnavailableError):
        await use_case(store)(replace(command(store), passed=False))
    assert not store.passes
    assert not store.intents


async def test_hidden_owner_may_reconsider_retained_pass_without_redisclosing_target() -> None:
    store = Store()
    send = command(store)
    first = await use_case(store)(send)
    own = store.sources[store.actor.session.account_id]
    lifecycle = own.setup.lifecycle
    assert lifecycle is not None
    hidden = lifecycle.with_visibility(hidden=True, at=NOW)
    store.sources[store.actor.session.account_id] = replace(
        own, setup=replace(own.setup, lifecycle=hidden)
    )
    del store.sources[TARGET]
    result = await use_case(store)(
        replace(
            send,
            passed=False,
            expected_version=first.version,
            intent_key=IntentKey("synthetic-review-1"),
        )
    )
    assert not result.passed


@pytest.mark.parametrize("state", ["banned", "deleted", "unverified"])
async def test_nonstudent_lifecycle_cannot_replay_private_history(state: str) -> None:
    store = Store()
    send = command(store)
    await use_case(store)(send)
    if state == "banned":
        store.actor = replace(store.actor, banned=True)
    elif state == "deleted":
        store.actor = replace(store.actor, deleted_at=NOW)
    else:
        store.actor = replace(store.actor, membership=None)
    with pytest.raises((StudentActionDeniedError, UnauthenticatedError)):
        await use_case(store)(send)


def test_private_command_rejects_invalid_version_and_impossible_undo() -> None:
    send = command(Store())
    for version in (True, -1):
        with pytest.raises(ValueError, match="nonnegative"):
            replace(send, expected_version=version)
    with pytest.raises(ValueError, match="only reconsiders"):
        replace(send, undo=True)
