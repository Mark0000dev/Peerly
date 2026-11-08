from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime
from uuid import UUID, uuid4

import pytest

from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import IdentitySnapshot, UnauthenticatedError
from studymate.application.profiles.help_subjects import (
    HelpIntent,
    HelpTransaction,
    SavedHelpSubjects,
    SaveHelpCommand,
    SaveOwnHelpSubjects,
)
from studymate.domain.catalogue import Subject
from studymate.domain.study_context import HelpRevision, HelpSubjects
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.identity_store import CREDENTIAL, NOW, IdentityStore


class Store:
    def __init__(self, *, expire_before_commit: bool = False) -> None:
        self.auth = IdentityStore()
        self.versions: dict[int, SavedHelpSubjects] = {}
        self.intents: dict[str, HelpIntent] = {}
        self.expire_before_commit = expire_before_commit

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[HelpTransaction]:
        versions, intents = self.versions.copy(), self.intents.copy()
        try:
            yield self
        except BaseException:
            self.versions, self.intents = versions, intents
            raise

    def authenticated(self, account_id: UUID) -> None:
        self.auth.authenticated(account_id)

    async def lock_identity(self, secret_digest: bytes) -> IdentitySnapshot | None:
        return await self.auth.lock_identity(secret_digest)

    async def now(self) -> datetime:
        return await self.auth.now()

    async def help_subjects(
        self, account_id: UUID, version: int | None = None
    ) -> SavedHelpSubjects | None:
        assert account_id == self.auth.actor.session.account_id
        return self.versions.get(version if version is not None else max(self.versions, default=0))

    async def help_intent(self, account_id: UUID, key: IntentKey) -> HelpIntent | None:
        assert account_id == self.auth.actor.session.account_id
        return self.intents.get(key.value)

    async def subjects(self, _subject_ids: tuple[UUID, ...]) -> tuple[Subject, ...]:
        return ()

    async def save_help(self, value: SavedHelpSubjects) -> None:
        self.versions[value.revision.version] = value

    async def remember_help_intent(
        self, account_id: UUID, key: IntentKey, intent: HelpIntent, at: datetime
    ) -> None:
        assert account_id == self.auth.actor.session.account_id
        assert at == self.auth.clock
        self.intents[key.value] = intent
        if self.expire_before_commit:
            self.auth.clock = self.auth.actor.session.expires_at


def command() -> SaveHelpCommand:
    return SaveHelpCommand(CREDENTIAL, HelpSubjects(), 0, IntentKey("synthetic-intent"))


async def test_help_expiry_rolls_back_revision_and_intent() -> None:
    store = Store(expire_before_commit=True)
    save = SaveOwnHelpSubjects(
        store, Sha256SessionHasher(), HmacIntentFingerprinter(bytes(range(32)))
    )
    with pytest.raises(UnauthenticatedError):
        await save(command())
    assert store.versions == {}
    assert store.intents == {}


async def test_corrupt_help_retry_result_never_becomes_empty_success() -> None:
    store = Store()
    save = SaveOwnHelpSubjects(
        store, Sha256SessionHasher(), HmacIntentFingerprinter(bytes(range(32)))
    )
    await save(command())
    store.versions.clear()
    with pytest.raises(RuntimeError, match="result is unavailable"):
        await save(command())


@pytest.mark.parametrize("version", [-1, True])
def test_help_expected_version_is_nonnegative_integer(version: int) -> None:
    with pytest.raises(ValueError, match="nonnegative"):
        replace(command(), expected_version=version)


def test_help_revision_and_labels_cannot_claim_invalid_history() -> None:
    with pytest.raises(ValueError, match="positive"):
        HelpRevision(uuid4(), 0, HelpSubjects(), NOW)
    with pytest.raises(ValueError, match="correspond"):
        SavedHelpSubjects(HelpRevision(uuid4(), 1, HelpSubjects(), NOW), ("Invented label",))
