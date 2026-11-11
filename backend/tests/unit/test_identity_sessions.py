from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from studymate.application.identity.sessions import (
    IdentitySnapshot,
    IdentityTransaction,
    Logout,
    ReadIdentity,
    SessionCredential,
    UnauthenticatedError,
)
from studymate.domain.identity import Session
from studymate.domain.membership import identity_capabilities
from studymate.infrastructure.security.session_digest import Sha256SessionHasher

DIGEST_BYTES = 32
NOW = datetime(2026, 11, 7, tzinfo=UTC)
CREDENTIAL = SessionCredential("a" * 43)


class IdentityStore:
    def __init__(self, snapshot: IdentitySnapshot | None) -> None:
        self.snapshot = snapshot
        self.revocations = 0
        self.closed = False
        self.authenticated_accounts: list[UUID] = []

    def authenticated(self, account_id: UUID) -> None:
        self.authenticated_accounts.append(account_id)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[IdentityTransaction]:
        try:
            yield self
        finally:
            self.closed = True

    async def lock_identity(self, secret_digest: bytes) -> IdentitySnapshot | None:
        assert len(secret_digest) == DIGEST_BYTES
        return self.snapshot

    async def now(self) -> datetime:
        return NOW

    async def revoke_session(self, session_id: UUID, at: datetime) -> None:
        assert self.snapshot is not None
        assert session_id == self.snapshot.session.id
        self.snapshot = replace(self.snapshot, session=self.snapshot.session.revoke(at))
        self.revocations += 1


def snapshot() -> IdentitySnapshot:
    return IdentitySnapshot(
        Session(UUID(int=1), UUID(int=2), NOW - timedelta(hours=1), NOW + timedelta(days=7)),
        membership=None,
        banned=False,
    )


@pytest.mark.parametrize("token", ["", "a" * 42, "a" * 44, "a" * 42 + "!", "\u212a" * 43])
def test_session_cookie_shape_is_bounded_and_ascii(token: str) -> None:
    with pytest.raises(UnauthenticatedError):
        SessionCredential(token)


async def test_high_entropy_session_hash_is_stable_and_private() -> None:
    hasher = Sha256SessionHasher()
    assert CREDENTIAL.value not in repr(CREDENTIAL)
    first = await hasher.digest(CREDENTIAL)
    assert first == await hasher.digest(CREDENTIAL)
    assert first != await hasher.digest(SessionCredential("b" * 43))
    assert len(first) == DIGEST_BYTES


async def test_google_authenticated_session_without_membership_is_limited() -> None:
    stored = snapshot()
    source = IdentityStore(stored)
    result = await ReadIdentity(source, Sha256SessionHasher())(CREDENTIAL)
    assert result == stored
    assert result.membership is None
    capabilities = identity_capabilities(
        membership=result.membership,
        banned=result.banned,
        activation_complete=False,
    )
    assert capabilities.can_verify_student_email
    assert not capabilities.can_use_student_features
    assert source.closed
    assert source.authenticated_accounts == [stored.session.account_id]


@pytest.mark.parametrize(
    "stored",
    [
        None,
        replace(snapshot(), session=replace(snapshot().session, expires_at=NOW)),
        replace(snapshot(), session=snapshot().session.revoke(NOW)),
    ],
)
async def test_missing_expired_revoked_sessions_have_same_failure(
    stored: IdentitySnapshot | None,
) -> None:
    source = IdentityStore(stored)
    with pytest.raises(UnauthenticatedError):
        await ReadIdentity(source, Sha256SessionHasher())(CREDENTIAL)
    assert source.closed
    assert source.authenticated_accounts == []


async def test_logout_is_idempotent_and_does_not_restore_credentials() -> None:
    source = IdentityStore(snapshot())
    logout = Logout(source, Sha256SessionHasher())
    await logout(CREDENTIAL)
    await logout(CREDENTIAL)
    assert source.revocations == 1
    with pytest.raises(UnauthenticatedError):
        await ReadIdentity(source, Sha256SessionHasher())(CREDENTIAL)


async def test_logout_unknown_session_is_harmless() -> None:
    source = IdentityStore(None)
    await Logout(source, Sha256SessionHasher())(CREDENTIAL)
    assert source.revocations == 0
