import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from studymate.application.identity.native_login import (
    BindNativeCallback,
    CancelNativeAttempt,
    ExchangeNativeAttempt,
    IdentifyNativeCallback,
    NativeAttempt,
    NativeLoginPendingError,
    NativeLoginRejectedError,
    NativeTransaction,
    RegisterNativeAttempt,
    proof_challenge,
    require_challenge,
)
from studymate.application.identity.sessions import IdentitySnapshot, SessionCredential
from studymate.domain.identity import Session
from studymate.infrastructure.security.login_vault import AeadLoginVault
from studymate.infrastructure.security.session_digest import Sha256SessionHasher

NOW = datetime(2026, 11, 12, tzinfo=UTC)
VERIFIER = "A" * 43
BROWSER = SessionCredential("B" * 43)
PROVISIONAL = SessionCredential("C" * 43)
HASHER = Sha256SessionHasher()


@dataclass
class MemoryNative:
    attempts: dict[UUID, NativeAttempt] = field(default_factory=dict)
    identities: dict[bytes, IdentitySnapshot] = field(default_factory=dict)
    clock: datetime = NOW
    fail_consumption: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    authenticated_accounts: list[UUID] = field(default_factory=list)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[NativeTransaction]:
        async with self.lock:
            attempts, identities = self.attempts.copy(), self.identities.copy()
            try:
                yield self
            except BaseException:
                self.attempts, self.identities = attempts, identities
                raise

    def authenticated(self, account_id: UUID) -> None:
        self.authenticated_accounts.append(account_id)

    async def lock_identity(self, secret_digest: bytes) -> IdentitySnapshot | None:
        return self.identities.get(secret_digest)

    async def now(self) -> datetime:
        return self.clock

    async def add_native(self, attempt: NativeAttempt) -> None:
        if attempt.id in self.attempts or any(
            row.browser_digest == attempt.browser_digest for row in self.attempts.values()
        ):
            raise NativeLoginRejectedError
        self.attempts[attempt.id] = attempt

    async def native_by_browser(self, digest: bytes) -> NativeAttempt | None:
        return next((row for row in self.attempts.values() if row.browser_digest == digest), None)

    async def native_by_id(self, attempt_id: UUID) -> NativeAttempt | None:
        return self.attempts.get(attempt_id)

    async def lock_native(self, attempt_id: UUID) -> NativeAttempt | None:
        return self.attempts.get(attempt_id)

    async def bind_native(self, attempt_id: UUID, source_digest: bytes) -> None:
        self.attempts[attempt_id] = replace(self.attempts[attempt_id], source_digest=source_digest)

    async def limit_session_expiry(self, session_id: UUID, expires_at: datetime) -> None:
        for digest, snapshot in self.identities.items():
            if snapshot.session.id == session_id:
                self.identities[digest] = replace(
                    snapshot,
                    session=replace(
                        snapshot.session, expires_at=min(snapshot.session.expires_at, expires_at)
                    ),
                )

    async def consume_native(self, attempt_id: UUID, at: datetime) -> None:
        if self.fail_consumption:
            raise OSError("synthetic commit failure")
        self.attempts[attempt_id] = replace(self.attempts[attempt_id], consumed_at=at)

    async def cancel_native(self, attempt_id: UUID, at: datetime) -> None:
        self.attempts[attempt_id] = replace(self.attempts[attempt_id], cancelled_at=at)

    async def add_session(self, session: Session, digest: bytes) -> None:
        self.identities[digest] = IdentitySnapshot(session, None, False)

    async def revoke_session(self, session_id: UUID, at: datetime) -> None:
        for digest, snapshot in self.identities.items():
            if snapshot.session.id == session_id:
                self.identities[digest] = replace(
                    snapshot, session=replace(snapshot.session, revoked_at=at)
                )


def exchange(memory: MemoryNative) -> ExchangeNativeAttempt:
    return ExchangeNativeAttempt(memory, HASHER, AeadLoginVault(bytes(range(32))))


async def prepared() -> tuple[MemoryNative, UUID]:
    memory = MemoryNative()
    attempt_id = uuid4()
    await RegisterNativeAttempt(memory, HASHER)(attempt_id, proof_challenge(VERIFIER), BROWSER)
    memory.identities[await HASHER.digest(PROVISIONAL)] = IdentitySnapshot(
        Session(uuid4(), uuid4(), NOW, NOW + timedelta(days=7)), None, False
    )
    return memory, attempt_id


async def bound() -> tuple[MemoryNative, UUID]:
    memory, attempt_id = await prepared()
    assert await BindNativeCallback(memory, HASHER)(BROWSER, PROVISIONAL)
    return memory, attempt_id


async def test_one_time_exchange_revokes_provisional_without_plaintext_storage() -> None:
    memory, attempt_id = await bound()
    minted = await exchange(memory)(attempt_id, VERIFIER)
    source = memory.identities[await HASHER.digest(PROVISIONAL)]
    assert source.session.revoked_at == NOW
    assert source.session.expires_at == memory.attempts[attempt_id].expires_at
    assert (
        memory.identities[await HASHER.digest(minted)].session.account_id
        == source.session.account_id
    )
    for secret in (VERIFIER, BROWSER.value, PROVISIONAL.value, minted.value):
        assert secret not in repr(memory.attempts[attempt_id])
    with pytest.raises(NativeLoginRejectedError):
        await exchange(memory)(attempt_id, VERIFIER)


async def test_pending_wrong_proof_and_unknown_id_never_grant_authority() -> None:
    memory, attempt_id = await prepared()
    with pytest.raises(NativeLoginPendingError):
        await exchange(memory)(attempt_id, VERIFIER)
    with pytest.raises(NativeLoginRejectedError):
        await exchange(memory)(attempt_id, "D" * 43)
    with pytest.raises(NativeLoginRejectedError):
        await exchange(memory)(uuid4(), VERIFIER)
    assert memory.attempts[attempt_id].consumed_at is None


@pytest.mark.parametrize("value", ["", "A" * 42, "A" * 129, "A" * 42 + "@", "\n" + "A" * 43])
def test_invalid_verifiers(value: str) -> None:
    with pytest.raises(NativeLoginRejectedError):
        proof_challenge(value)


@pytest.mark.parametrize("value", ["A" * 42, "!" * 43, "A" * 42 + "B", "A" * 43 + "="])
def test_invalid_challenges(value: str) -> None:
    with pytest.raises(NativeLoginRejectedError):
        require_challenge(value)


def test_rfc7636_s256_vector() -> None:
    assert (
        proof_challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk")
        == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    )


async def test_expiry_and_duplicate_registration() -> None:
    memory, attempt_id = await bound()
    with pytest.raises(NativeLoginRejectedError):
        await RegisterNativeAttempt(memory, HASHER)(attempt_id, proof_challenge(VERIFIER), BROWSER)
    memory.clock = memory.attempts[attempt_id].expires_at
    with pytest.raises(NativeLoginRejectedError):
        await exchange(memory)(attempt_id, VERIFIER)


@pytest.mark.parametrize("reason", ["deleted", "revoked", "expired", "missing"])
async def test_rechecks_live_identity(reason: str) -> None:
    memory, attempt_id = await bound()
    digest = await HASHER.digest(PROVISIONAL)
    old = memory.identities[digest]
    if reason == "deleted":
        memory.identities[digest] = replace(old, deleted_at=NOW)
    elif reason == "revoked":
        memory.identities[digest] = replace(old, session=replace(old.session, revoked_at=NOW))
    elif reason == "expired":
        memory.identities[digest] = replace(
            old, session=replace(old.session, issued_at=NOW - timedelta(seconds=1), expires_at=NOW)
        )
    else:
        del memory.identities[digest]
    with pytest.raises(NativeLoginRejectedError):
        await exchange(memory)(attempt_id, VERIFIER)
    assert memory.attempts[attempt_id].consumed_at is None


async def test_browser_binding_and_ordinary_web_are_distinct() -> None:
    memory, attempt_id = await prepared()
    binder = BindNativeCallback(memory, HASHER)
    assert not await binder(SessionCredential("D" * 43), PROVISIONAL)
    assert await binder(BROWSER, PROVISIONAL)
    with pytest.raises(NativeLoginRejectedError):
        await binder(BROWSER, PROVISIONAL)
    assert memory.attempts[attempt_id].source_digest == await HASHER.digest(PROVISIONAL)


async def test_existing_other_session_rejected_without_cross_actor_locking() -> None:
    memory, attempt_id = await bound()
    with pytest.raises(NativeLoginRejectedError):
        await exchange(memory)(attempt_id, VERIFIER, SessionCredential("D" * 43))
    assert memory.attempts[attempt_id].consumed_at is None


async def test_consumption_failure_rolls_back_new_session_and_revocation() -> None:
    memory, attempt_id = await bound()
    original = memory.identities.copy()
    memory.fail_consumption = True
    with pytest.raises(OSError, match="synthetic commit failure"):
        await exchange(memory)(attempt_id, VERIFIER)
    assert memory.identities == original
    assert memory.attempts[attempt_id].consumed_at is None


async def test_concurrent_exchange_has_one_winner() -> None:
    memory, attempt_id = await bound()
    results = await asyncio.gather(
        exchange(memory)(attempt_id, VERIFIER),
        exchange(memory)(attempt_id, VERIFIER),
        return_exceptions=True,
    )
    assert sum(isinstance(result, SessionCredential) for result in results) == 1
    assert sum(isinstance(result, NativeLoginRejectedError) for result in results) == 1


async def test_native_callback_identification_preserves_ordinary_web_mode() -> None:
    memory, _ = await prepared()
    identify = IdentifyNativeCallback(memory, HASHER)
    assert not await identify(None)
    assert not await identify(SessionCredential("D" * 43))
    assert await identify(BROWSER)


async def test_cancelled_attempt_is_terminal_and_cannot_adopt_a_callback() -> None:
    memory, attempt_id = await prepared()
    cancel = CancelNativeAttempt(memory, HASHER)
    await cancel(SessionCredential("D" * 43))
    await cancel(BROWSER)
    await cancel(BROWSER)
    with pytest.raises(NativeLoginRejectedError):
        await exchange(memory)(attempt_id, VERIFIER)
    with pytest.raises(NativeLoginRejectedError):
        await BindNativeCallback(memory, HASHER)(BROWSER, PROVISIONAL)
    assert memory.attempts[attempt_id].cancelled_at == NOW


async def test_cancel_does_not_revoke_an_already_consumed_native_session() -> None:
    memory, attempt_id = await bound()
    minted = await exchange(memory)(attempt_id, VERIFIER)
    await CancelNativeAttempt(memory, HASHER)(BROWSER)
    assert memory.attempts[attempt_id].cancelled_at is None
    assert memory.identities[await HASHER.digest(minted)].session.revoked_at is None


async def test_callback_identity_retired_before_binding_is_a_uniform_native_failure() -> None:
    memory, attempt_id = await prepared()
    digest = await HASHER.digest(PROVISIONAL)
    memory.identities[digest] = replace(memory.identities[digest], deleted_at=NOW)
    with pytest.raises(NativeLoginRejectedError):
        await BindNativeCallback(memory, HASHER)(BROWSER, PROVISIONAL)
    assert memory.attempts[attempt_id].source_digest is None
