from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import IdentitySnapshot, SessionCredential
from studymate.application.notification_preferences.preferences import (
    ChooseOwnNotificationPreference,
    ChoosePreferenceCommand,
    PreferenceIntent,
    PreferenceTransaction,
    PreferenceVersionConflictError,
    ReadOwnNotificationPreference,
)
from studymate.domain.identity import Session, StudentEmail
from studymate.domain.membership import Membership
from studymate.domain.notification_preferences.state import NotificationMode, NotificationPreference
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter

SECOND_VERSION = 2
NOW = datetime(2026, 11, 9, tzinfo=UTC)
CREDENTIAL = SessionCredential("a" * 43)


class Hasher:
    async def digest(self, credential: SessionCredential) -> bytes:
        return credential.value.encode()


class Store:
    def __init__(self) -> None:
        self.current = NotificationPreference()
        self.intents: dict[IntentKey, PreferenceIntent] = {}
        self.owner = uuid4()
        self.saves = 0

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[PreferenceTransaction]:
        yield self

    def authenticated(self, account_id: UUID) -> None:
        assert account_id == self.owner

    async def lock_identity(self, secret_digest: bytes) -> IdentitySnapshot:
        assert secret_digest == CREDENTIAL.value.encode()
        return IdentitySnapshot(
            Session(uuid4(), self.owner, NOW, NOW + timedelta(days=1), None),
            Membership(StudentEmail("student@mail.apu.edu.my"), NOW, None),
            False,
        )

    async def now(self) -> datetime:
        return NOW

    async def preference(self, account_id: UUID) -> NotificationPreference:
        assert account_id == self.owner
        return self.current

    async def intent(self, account_id: UUID, key: IntentKey) -> PreferenceIntent | None:
        assert account_id == self.owner
        return self.intents.get(key)

    async def save(self, account_id: UUID, result: NotificationPreference) -> None:
        assert account_id == self.owner
        self.current = result
        self.saves += 1

    async def remember(
        self, account_id: UUID, key: IntentKey, intent: PreferenceIntent, at: datetime
    ) -> None:
        assert account_id == self.owner
        assert at == NOW
        self.intents[key] = intent


async def test_explicit_update_replay_preserves_original_result_after_switching_back() -> None:
    store = Store()
    choose = ChooseOwnNotificationPreference(store, Hasher(), HmacIntentFingerprinter(b"k" * 32))
    initial = await ReadOwnNotificationPreference(store, Hasher())(CREDENTIAL)
    assert initial == NotificationPreference()
    first = ChoosePreferenceCommand(
        CREDENTIAL, NotificationMode.ALL_UPDATES, 0, IntentKey("intent_001")
    )
    result = await choose(first)
    assert result.version == 1
    second = await choose(
        ChoosePreferenceCommand(
            CREDENTIAL, NotificationMode.MESSAGES_AND_REQUESTS, 1, IntentKey("intent_002")
        )
    )
    assert second.version == SECOND_VERSION
    assert await choose(first) == result
    assert store.current == second
    assert store.saves == SECOND_VERSION
    with pytest.raises(IdempotencyConflictError):
        await choose(
            ChoosePreferenceCommand(
                CREDENTIAL, NotificationMode.MESSAGES_AND_REQUESTS, 0, first.intent_key
            )
        )
    with pytest.raises(PreferenceVersionConflictError) as error:
        await choose(
            ChoosePreferenceCommand(
                CREDENTIAL, NotificationMode.ALL_UPDATES, 0, IntentKey("intent_003")
            )
        )
    assert error.value.current_version == SECOND_VERSION


async def test_default_noop_replay_is_stable_after_later_choice() -> None:
    store = Store()
    choose = ChooseOwnNotificationPreference(store, Hasher(), HmacIntentFingerprinter(b"k" * 32))
    noop = ChoosePreferenceCommand(
        CREDENTIAL, NotificationMode.MESSAGES_AND_REQUESTS, 0, IntentKey("intent_001")
    )
    assert await choose(noop) == NotificationPreference()
    await choose(
        ChoosePreferenceCommand(
            CREDENTIAL, NotificationMode.ALL_UPDATES, 0, IntentKey("intent_002")
        )
    )
    assert await choose(noop) == NotificationPreference()
    assert store.saves == 1


@pytest.mark.parametrize("version", [-1, True])
def test_command_rejects_invalid_cas_version(version: int) -> None:
    with pytest.raises(ValueError, match="nonnegative"):
        ChoosePreferenceCommand(
            CREDENTIAL, NotificationMode.ALL_UPDATES, version, IntentKey("intent_001")
        )
