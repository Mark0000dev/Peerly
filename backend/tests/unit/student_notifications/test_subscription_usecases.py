from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import (
    IdentitySnapshot,
    SessionCredential,
    StudentActionDeniedError,
)
from studymate.application.student_notifications.capabilities import ReadOwnDelivery
from studymate.application.student_notifications.subscriptions import (
    DeliveryUnavailableError,
    RegisterDeviceCommand,
    RegisterOwnDelivery,
    SubscriptionIntent,
    SubscriptionTransaction,
    SubscriptionVersionError,
)
from studymate.domain.identity import Session, StudentEmail
from studymate.domain.membership import Membership
from studymate.domain.student_notifications.capabilities import (
    Capabilities,
    DeviceState,
    Platform,
    Registration,
)
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter

EXPECTED_SAVES = 2
NOW = datetime(2026, 11, 13, tzinfo=UTC)
CREDENTIAL = SessionCredential("a" * 43)


class Hasher:
    async def digest(self, credential: SessionCredential) -> bytes:
        return credential.value.encode()


class Store:
    def __init__(self) -> None:
        self.owner = uuid4()
        self.session_id = uuid4()
        self.enrolled_session_id: UUID | None = None
        self.current: DeviceState | None = None
        self.intents: dict[IntentKey, SubscriptionIntent] = {}
        self.banned = False
        self.saves = 0

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SubscriptionTransaction]:
        yield self

    def authenticated(self, account_id: UUID) -> None:
        assert account_id == self.owner

    async def lock_identity(self, secret_digest: bytes) -> IdentitySnapshot:
        assert secret_digest == CREDENTIAL.value.encode()
        return IdentitySnapshot(
            Session(self.session_id, self.owner, NOW, NOW + timedelta(days=1), None),
            Membership(StudentEmail("synthetic@mail.apu.edu.my"), NOW, None),
            self.banned,
        )

    async def now(self) -> datetime:
        return NOW

    async def read(self, account_id: UUID, installation: UUID) -> DeviceState | None:
        assert account_id == self.owner
        return (
            self.current
            if self.current is not None and self.current.installation_id == installation
            else None
        )

    async def replay(self, account_id: UUID, key: IntentKey) -> SubscriptionIntent | None:
        assert account_id == self.owner
        return self.intents.get(key)

    async def save(
        self, account_id: UUID, session_id: UUID, value: Registration, prior: DeviceState | None
    ) -> DeviceState:
        assert account_id == self.owner
        assert session_id == self.session_id
        self.enrolled_session_id = session_id
        self.saves += 1
        self.current = DeviceState(
            value.installation_id,
            value.platform,
            1 if prior is None else prior.version + 1,
            value.enabled,
            value.timezone,
        )
        return self.current

    async def remember(self, account_id: UUID, key: IntentKey, intent: SubscriptionIntent) -> None:
        assert account_id == self.owner
        self.intents[key] = intent


async def test_disable_is_immediate_and_replay_does_not_reenable_or_require_live_provider() -> None:
    store = Store()
    choose = RegisterOwnDelivery(
        store, Hasher(), HmacIntentFingerprinter(bytes(range(32))), Capabilities(android=True)
    )
    value = Registration(uuid4(), Platform.ANDROID, True, "Asia/Kuala_Lumpur", "synthetic-token")
    first = RegisterDeviceCommand(CREDENTIAL, value, 0, IntentKey("register_001"))
    enabled = await choose(first)
    disabled = await choose(
        RegisterDeviceCommand(
            CREDENTIAL, replace(value, enabled=False, endpoint=None), 1, IntentKey("disable_001")
        )
    )
    assert not disabled.enabled
    assert await replace(choose, capabilities=Capabilities())(first) == enabled
    assert store.current == disabled
    assert store.saves == EXPECTED_SAVES
    assert store.enrolled_session_id == store.session_id
    with pytest.raises(IdempotencyConflictError):
        await choose(replace(first, registration=replace(value, timezone="UTC")))
    with pytest.raises(SubscriptionVersionError):
        await choose(replace(first, intent_key=IntentKey("new_stale_001")))


async def test_actor_guard_precedes_provider_state_and_never_reads_secrets() -> None:
    store = Store()
    value = Registration(uuid4(), Platform.ANDROID, True, None, "synthetic-token")
    usecase = RegisterOwnDelivery(
        store, Hasher(), HmacIntentFingerprinter(bytes(range(32))), Capabilities()
    )
    store.banned = True
    with pytest.raises(StudentActionDeniedError):
        await usecase(RegisterDeviceCommand(CREDENTIAL, value, 0, IntentKey("register_001")))
    store.banned = False
    with pytest.raises(DeliveryUnavailableError):
        await usecase(RegisterDeviceCommand(CREDENTIAL, value, 0, IntentKey("register_001")))
    status = await ReadOwnDelivery(store, Hasher(), Capabilities())(
        CREDENTIAL, value.installation_id
    )
    assert status.device is None
    assert not status.capability.android
