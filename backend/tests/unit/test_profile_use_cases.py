from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID

import pytest

from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import (
    UnauthenticatedError,
)
from studymate.application.profiles.basics import (
    ProfileIntent,
    ProfileTransaction,
    SaveOwnProfile,
    SaveProfileCommand,
)
from studymate.domain.profiles import DisplayName, OnboardingTask, ProfileBasics, ProfileRevision
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.identity_store import CREDENTIAL, IdentityStore


class Store(IdentityStore):
    def __init__(self, *, expire_before_commit: bool = False) -> None:
        super().__init__()
        self.versions: dict[int, ProfileRevision] = {}
        self.intents: dict[str, ProfileIntent] = {}
        self.expire_before_commit = expire_before_commit

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[ProfileTransaction]:
        versions, intents = self.versions.copy(), self.intents.copy()
        try:
            yield self
        except BaseException:
            self.versions, self.intents = versions, intents
            raise

    async def profile(self, account_id: UUID, version: int | None = None) -> ProfileRevision | None:
        assert account_id == self.actor.session.account_id
        return self.versions.get(version if version is not None else max(self.versions, default=0))

    async def profile_intent(self, account_id: UUID, key: IntentKey) -> ProfileIntent | None:
        assert account_id == self.actor.session.account_id
        return self.intents.get(key.value)

    async def save_profile(self, revision: ProfileRevision) -> None:
        self.versions[revision.version] = revision

    async def remember_profile_intent(
        self, account_id: UUID, key: IntentKey, intent: ProfileIntent, at: datetime
    ) -> None:
        assert account_id == self.actor.session.account_id
        assert at == self.clock
        self.intents[key.value] = intent
        if self.expire_before_commit:
            self.clock = self.actor.session.expires_at


def command(version: int = 0) -> SaveProfileCommand:
    return SaveProfileCommand(
        CREDENTIAL,
        ProfileBasics(DisplayName("Synthetic draft")),
        OnboardingTask.FIND_HELP,
        version,
        IntentKey("synthetic-intent"),
    )


async def test_expiry_before_commit_rolls_back_saved_step_and_retry_result() -> None:
    store = Store(expire_before_commit=True)
    save = SaveOwnProfile(store, Sha256SessionHasher(), HmacIntentFingerprinter(bytes(range(32))))
    with pytest.raises(UnauthenticatedError):
        await save(command())
    assert store.versions == {}
    assert store.intents == {}


async def test_corrupted_retry_result_does_not_become_an_empty_success() -> None:
    store = Store()
    fingerprinter = HmacIntentFingerprinter(bytes(range(32)))
    save = SaveOwnProfile(store, Sha256SessionHasher(), fingerprinter)
    submitted = command()
    await save(submitted)
    store.versions.clear()
    with pytest.raises(RuntimeError, match="result is unavailable"):
        await save(submitted)


@pytest.mark.parametrize("version", [-1, True])
def test_expected_revision_rejects_negative_and_boolean_values(version: int) -> None:
    with pytest.raises(ValueError, match="nonnegative integer"):
        command(version)


async def test_intent_fingerprints_are_private_purpose_bound_and_unambiguous() -> None:
    fingerprinter = HmacIntentFingerprinter(bytes(range(32)))
    first = await fingerprinter.fingerprint(("profile.save.v1", "ab", "c"))
    assert first == await fingerprinter.fingerprint(("profile.save.v1", "ab", "c"))
    assert first != await fingerprinter.fingerprint(("profile.save.v1", "a", "bc"))
    assert first != await fingerprinter.fingerprint(("goal.save.v1", "ab", "c"))
    with pytest.raises(ValueError, match="32 bytes"):
        HmacIntentFingerprinter(b"short")
