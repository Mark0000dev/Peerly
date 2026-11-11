from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from studymate.application.discovery.profiles import (
    DiscoveryProfileSource,
    DiscoveryProfileTransaction,
    DiscoveryProfileUnavailableError,
    ReadDiscoveryProfile,
)
from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.application.profiles.goals import SavedGoal
from studymate.application.profiles.onboarding import ProfileSetupSnapshot
from studymate.application.safety.blocks import OwnBlockResult
from studymate.domain.discovery_freshness import DiscoveryExposure
from studymate.domain.media import PhotoRevision
from studymate.domain.onboarding import ProfileLifecycle
from studymate.domain.profiles import DisplayName, OnboardingTask, ProfileBasics, ProfileRevision
from studymate.domain.reports import ProfileAccessContext
from studymate.domain.study_context import CustomSubjectRef, GoalContent, StudyGoal
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.identity_store import CREDENTIAL, NOW, IdentityStore

TARGET = UUID(int=3)


class Store(IdentityStore):
    def __init__(self) -> None:
        super().__init__()
        self.actor = replace(self.actor, activation_complete=True)
        self.sources: dict[UUID, DiscoveryProfileSource] = {
            account_id: source(account_id, self)
            for account_id in (self.actor.session.account_id, TARGET)
        }
        self.blocked = False
        self.own_block = OwnBlockResult(TARGET, False, 0, None)
        self.contexts: list[ProfileAccessContext] = []
        self.expire_on_save = False

    @asynccontextmanager
    async def transaction(self, target_id: UUID) -> AsyncIterator[DiscoveryProfileTransaction]:
        assert target_id.int > 0
        previous = self.contexts.copy()
        try:
            yield self
        except BaseException:
            self.contexts = previous
            raise

    async def profile_source(self, account_id: UUID) -> DiscoveryProfileSource | None:
        return self.sources.get(account_id)

    async def pair_blocked(self, actor_id: UUID, target_id: UUID) -> bool:
        assert actor_id == self.actor.session.account_id
        assert target_id == TARGET
        return self.blocked

    async def own_block_state(self, actor_id: UUID, target_id: UUID) -> OwnBlockResult:
        assert actor_id == self.actor.session.account_id
        assert target_id == TARGET
        return self.own_block

    async def remember_profile_access(self, context: ProfileAccessContext) -> None:
        self.contexts.append(context)
        if self.expire_on_save:
            self.clock = self.actor.session.expires_at


def source(account_id: UUID, store: IdentityStore) -> DiscoveryProfileSource:
    goal = StudyGoal(
        uuid4(),
        account_id,
        1,
        GoalContent(CustomSubjectRef("Synthetic self-declared topic")),
        NOW,
        NOW,
    )
    return DiscoveryProfileSource(
        ProfileSetupSnapshot(
            account_id,
            ProfileRevision(
                account_id,
                1,
                ProfileBasics(DisplayName("Synthetic peer")),
                OnboardingTask.FIND_HELP,
                NOW,
            ),
            PhotoRevision(account_id, 1, uuid4(), NOW),
            SavedGoal(goal, "Synthetic self-declared topic"),
            None,
            ProfileLifecycle(account_id, NOW, 1, None, NOW),
        ),
        store.actor.membership,
        True,
        False,
        False,
    )


async def test_discovery_profile_discloses_exact_source_refs_without_membership_data() -> None:
    store = Store()
    result = await ReadDiscoveryProfile(store, Sha256SessionHasher())(CREDENTIAL, TARGET)
    target = store.sources[TARGET]
    assert result.profile == target.setup.profile
    assert result.access_context.viewer_id == store.actor.session.account_id
    assert result.access_context.snapshot.account_id == TARGET
    assert result.access_context.snapshot.profile_version == result.profile.version
    assert result.access_context.snapshot.photo_version == result.photo.version
    assert result.goal is not None
    assert result.access_context.snapshot.goal_id == result.goal.goal.id
    assert store.contexts == [result.access_context]
    assert "mail.apu.edu.my" not in repr(result)
    assert "Synthetic peer" not in repr(result)


@pytest.mark.parametrize("state", ["hidden", "photo_missing", "context_missing", "not_activated"])
async def test_own_profile_eligibility_is_checked_before_disclosing_peer(state: str) -> None:
    store = Store()
    own_id = store.actor.session.account_id
    own = store.sources[own_id]
    setup = own.setup
    if state == "hidden":
        assert setup.lifecycle is not None
        setup = replace(setup, lifecycle=setup.lifecycle.with_visibility(hidden=True, at=NOW))
    elif state == "photo_missing":
        setup = replace(setup, photo=None)
    elif state == "context_missing":
        setup = replace(setup, goal=None)
    else:
        store.actor = replace(store.actor, activation_complete=False)
    store.sources[own_id] = replace(own, setup=setup)
    with pytest.raises(StudentActionDeniedError):
        await ReadDiscoveryProfile(store, Sha256SessionHasher())(CREDENTIAL, TARGET)
    assert not store.contexts


@pytest.mark.parametrize(
    "state", ["hidden", "banned", "deleted", "unverified", "unknown", "blocked"]
)
async def test_peer_unavailability_is_neutral_and_never_issues_context(state: str) -> None:
    store = Store()
    target = store.sources[TARGET]
    if state == "hidden":
        assert target.setup.lifecycle is not None
        target = replace(
            target,
            setup=replace(
                target.setup, lifecycle=target.setup.lifecycle.with_visibility(hidden=True, at=NOW)
            ),
        )
    elif state == "banned":
        target = replace(target, banned=True)
    elif state == "deleted":
        target = replace(target, deleted=True)
    elif state == "unverified":
        target = replace(target, membership=None)
    elif state == "blocked":
        store.blocked = True
    store.sources[TARGET] = target
    if state == "unknown":
        del store.sources[TARGET]
    with pytest.raises(DiscoveryProfileUnavailableError):
        await ReadDiscoveryProfile(store, Sha256SessionHasher())(CREDENTIAL, TARGET)
    assert not store.contexts


async def test_exposure_pause_alone_cannot_restrict_direct_profile_read_or_confirm_it() -> None:
    store = Store()
    old = NOW - timedelta(days=40)
    for account_id, value in tuple(store.sources.items()):
        store.sources[account_id] = replace(
            value,
            setup=replace(
                value.setup,
                exposure=DiscoveryExposure(account_id, old, old, old + timedelta(days=30)),
            ),
        )
    original = store.sources.copy()
    await ReadDiscoveryProfile(store, Sha256SessionHasher())(CREDENTIAL, TARGET)
    assert store.sources == original


async def test_profile_context_write_rolls_back_when_session_expires() -> None:
    store = Store()
    store.expire_on_save = True
    with pytest.raises(UnauthenticatedError):
        await ReadDiscoveryProfile(store, Sha256SessionHasher())(CREDENTIAL, TARGET)
    assert not store.contexts


async def test_self_profile_cannot_issue_peer_disclosure_context() -> None:
    store = Store()
    with pytest.raises(DiscoveryProfileUnavailableError):
        await ReadDiscoveryProfile(store, Sha256SessionHasher())(
            CREDENTIAL, store.actor.session.account_id
        )
    assert not store.contexts


async def test_public_profile_returns_actual_own_unblocked_revision_for_future_cas() -> None:
    store = Store()
    store.own_block = OwnBlockResult(TARGET, False, 2, NOW)
    result = await ReadDiscoveryProfile(store, Sha256SessionHasher())(CREDENTIAL, TARGET)
    assert result.own_block == store.own_block
