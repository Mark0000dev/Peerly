"""Canonical Logout composed with an atomic, installation-scoped transaction port."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from studymate.application.identity.sessions import IdentitySnapshot, SessionCredential
from studymate.application.student_notifications.subscriptions import (
    InstallationLogoutTransaction,
    LogoutInstallation,
    RetirementDisposition,
)
from studymate.domain.identity import Session

NOW = datetime(2026, 11, 14, tzinfo=UTC)
CREDENTIAL = SessionCredential("a" * 43)


class Hasher:
    async def digest(self, credential: SessionCredential) -> bytes:
        return credential.value.encode()


class Store:
    def __init__(self) -> None:
        self.account_id, self.installation, self.enrollment = (
            uuid4(),
            uuid4(),
            uuid4(),
        )
        self.identity: IdentitySnapshot | None = IdentitySnapshot(
            Session(
                self.enrollment,
                self.account_id,
                NOW - timedelta(hours=1),
                NOW + timedelta(days=1),
                None,
            ),
            None,
            False,
        )
        self.enabled = True
        self.retired = False
        self.revoked = False
        self.fail_revoke = False
        self.cancel_revoke = False
        self.events: list[str] = []

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[InstallationLogoutTransaction]:
        before = (self.enabled, self.retired, self.revoked)
        try:
            yield self
        except (RuntimeError, asyncio.CancelledError):
            self.enabled, self.retired, self.revoked = before
            raise
        self.events.append("commit")

    def authenticated(self, account_id: UUID) -> None:
        assert account_id == self.account_id
        self.events.append("authenticated")

    async def lock_identity(self, digest: bytes) -> IdentitySnapshot | None:
        assert digest == CREDENTIAL.value.encode()
        self.events.append("identity_locked")
        return self.identity

    async def now(self) -> datetime:
        return NOW

    async def retire_installation(
        self,
        account_id: UUID,
        session_id: UUID,
        installation_id: UUID | None,
        at: datetime,
    ) -> bool:
        assert self.events[0] == "identity_locked"
        assert account_id == self.account_id
        assert at == NOW
        self.events.append("retire")
        if session_id != self.enrollment or installation_id != self.installation:
            return False
        self.enabled, self.retired = (False, True)
        return True

    async def revoke_session(self, session_id: UUID, at: datetime) -> None:
        assert self.identity is not None
        assert session_id == self.identity.session.id
        assert at == NOW
        self.events.append("revoke")
        if self.fail_revoke:
            raise RuntimeError("Synthetic revoke failure")
        if self.cancel_revoke:
            raise asyncio.CancelledError
        self.revoked = True


async def test_active_nonstudent_can_atomically_retire_and_logout() -> None:
    store = Store()
    assert (
        await LogoutInstallation(store, Hasher())(CREDENTIAL, store.installation)
        == RetirementDisposition.RETIRED
    )
    assert store.retired
    assert store.revoked
    assert not store.enabled
    assert store.events == [
        "identity_locked",
        "authenticated",
        "retire",
        "revoke",
        "commit",
    ]


@pytest.mark.parametrize("mismatch", ["installation", "enrollment"])
async def test_foreign_installation_or_newer_enrollment_survives_old_logout(
    mismatch: str,
) -> None:
    store = Store()
    installation = store.installation
    if mismatch == "installation":
        installation = uuid4()
    else:
        store.enrollment = uuid4()
    assert (
        await LogoutInstallation(store, Hasher())(CREDENTIAL, installation)
        == RetirementDisposition.UNCONFIRMED
    )
    assert store.enabled
    assert not store.retired
    assert store.revoked


@pytest.mark.parametrize("state", ["missing", "expired", "revoked", "deleted"])
async def test_stale_identity_never_claims_installation_retired(state: str) -> None:
    store = Store()
    assert store.identity is not None
    if state == "missing":
        store.identity = None
    elif state == "deleted":
        store.identity = replace(store.identity, deleted_at=NOW)
    else:
        value = (
            replace(store.identity.session, expires_at=NOW)
            if state == "expired"
            else replace(store.identity.session, revoked_at=NOW)
        )
        store.identity = replace(store.identity, session=value)
    assert (
        await LogoutInstallation(store, Hasher())(CREDENTIAL, store.installation)
        == RetirementDisposition.UNCONFIRMED
    )
    assert store.enabled
    assert not store.retired
    assert "retire" not in store.events
    assert store.revoked == (state in ("expired", "deleted"))


@pytest.mark.parametrize("cancel", [False, True])
async def test_failure_or_cancellation_rolls_back_both_retirement_and_revocation(
    cancel: bool,
) -> None:
    store = Store()
    store.fail_revoke, store.cancel_revoke = (not cancel, cancel)
    expected = asyncio.CancelledError if cancel else RuntimeError
    with pytest.raises(expected):
        await LogoutInstallation(store, Hasher())(CREDENTIAL, store.installation)
    assert store.enabled
    assert not store.retired
    assert not store.revoked
    assert "commit" not in store.events
