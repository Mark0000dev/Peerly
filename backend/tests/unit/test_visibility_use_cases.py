from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime
from uuid import UUID

import pytest

from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.profiles.goals import SavedGoal
from studymate.application.profiles.onboarding import ProfileSetupSnapshot
from studymate.application.profiles.visibility import (
    ChangeOwnVisibility,
    ChangeVisibilityCommand,
    VisibilityIntent,
    VisibilityTransaction,
)
from studymate.domain.discovery_freshness import ExposureConfirmation
from studymate.domain.onboarding import ProfileLifecycle
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.identity_store import CREDENTIAL, IdentityStore
from tests.unit.test_onboarding import activation


class Store(IdentityStore):
    def __init__(self) -> None:
        super().__init__()
        source = activation()
        self.actor = replace(
            self.actor,
            session=replace(self.actor.session, account_id=source.profile.account_id),
            registration=source.registration,
            activation_complete=True,
        )
        assert source.goal is not None
        self.snapshot = ProfileSetupSnapshot(
            source.profile.account_id,
            source.profile,
            source.photo,
            SavedGoal(source.goal, "Synthetic topic"),
            None,
            ProfileLifecycle(
                source.profile.account_id, source.completed_at, 1, None, source.completed_at
            ),
        )
        self.revisions: dict[int, ProfileLifecycle] = {}
        self.intents: dict[str, VisibilityIntent] = {}
        self.expire_before_commit = False

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[VisibilityTransaction]:
        snapshot, revisions, intents = self.snapshot, self.revisions.copy(), self.intents.copy()
        try:
            yield self
        except BaseException:
            self.snapshot, self.revisions, self.intents = snapshot, revisions, intents
            raise

    async def setup_snapshot(self, account_id: UUID) -> ProfileSetupSnapshot:
        assert account_id == self.snapshot.account_id
        return self.snapshot

    async def visibility_revision(self, account_id: UUID, version: int) -> ProfileLifecycle:
        assert account_id == self.snapshot.account_id
        return self.revisions[version]

    async def visibility_intent(self, account_id: UUID, key: IntentKey) -> VisibilityIntent | None:
        assert account_id == self.snapshot.account_id
        return self.intents.get(key.value)

    async def confirm_discovery_exposure(
        self,
        account_id: UUID,
        key: IntentKey,
        at: datetime,
    ) -> ExposureConfirmation | None:
        assert account_id == self.snapshot.account_id
        assert key.value
        assert at == self.clock
        return None

    async def save_visibility(self, lifecycle: ProfileLifecycle) -> None:
        self.revisions[lifecycle.visibility_version] = lifecycle
        self.snapshot = replace(self.snapshot, lifecycle=lifecycle)

    async def remember_visibility_intent(
        self, account_id: UUID, key: IntentKey, intent: VisibilityIntent, at: datetime
    ) -> None:
        assert account_id == self.snapshot.account_id
        assert at == self.clock
        self.intents[key.value] = intent
        if self.expire_before_commit:
            self.clock = self.actor.session.expires_at


async def test_visibility_session_expiry_rolls_back_revision_and_intent() -> None:
    store = Store()
    store.expire_before_commit = True
    initial = store.snapshot
    change = ChangeOwnVisibility(
        store, Sha256SessionHasher(), HmacIntentFingerprinter(bytes(range(32)))
    )
    with pytest.raises(UnauthenticatedError):
        await change(ChangeVisibilityCommand(CREDENTIAL, True, 1, IntentKey("synthetic-intent")))
    assert store.snapshot == initial
    assert store.revisions == {}
    assert store.intents == {}


@pytest.mark.parametrize("version", [0, -1, True])
def test_visibility_expected_version_rejects_invalid_values(version: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        ChangeVisibilityCommand(CREDENTIAL, True, version, IntentKey("synthetic-intent"))
