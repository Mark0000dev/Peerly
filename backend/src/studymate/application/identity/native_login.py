"""Proof-bound native handoff. No provider transport, plaintext storage or token URLs."""

import base64
import hashlib
import hmac
import re
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from studymate.application.identity.google import GoogleRejectedError, GoogleUnavailableError
from studymate.application.identity.login import (
    SESSION_LIFETIME,
    BeginGoogleLogin,
    CallbackRateLimitedError,
    GoogleCallbackCommand,
    LoginCompleted,
    LoginStarted,
    LoginVault,
)
from studymate.application.identity.sessions import (
    IdentityTransaction,
    SessionCredential,
    SessionHasher,
    UnauthenticatedError,
    require_session_identity,
)
from studymate.domain.identity import Session

NATIVE_LIFETIME = timedelta(minutes=5)
_PROOF = re.compile(r"[A-Za-z0-9_-]{43}")
_VERIFIER = re.compile(r"[A-Za-z0-9._~-]{43,128}")


class NativeLoginRejectedError(Exception):
    """Uniform failure without disclosing identities or proof material."""


class NativeLoginPendingError(Exception):
    """No authenticated callback yet; never an implicit success."""


def proof_challenge(verifier: str) -> str:
    if _VERIFIER.fullmatch(verifier) is None:
        raise NativeLoginRejectedError
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )


def require_challenge(challenge: str) -> None:
    if _PROOF.fullmatch(challenge) is None:
        raise NativeLoginRejectedError
    # Reject noncanonical trailing base64 pad bits as well as malformed text.
    digest = base64.urlsafe_b64decode(challenge + "=")
    if base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii") != challenge:
        raise NativeLoginRejectedError


@dataclass(frozen=True, slots=True)
class NativeAttempt:
    id: UUID
    challenge: str = field(repr=False)
    browser_digest: bytes = field(repr=False)
    created_at: datetime
    expires_at: datetime
    source_digest: bytes | None = field(default=None, repr=False)
    consumed_at: datetime | None = None
    cancelled_at: datetime | None = None


class NativeTransaction(IdentityTransaction, Protocol):
    async def add_native(self, attempt: NativeAttempt) -> None:
        """Unique ID + browser_digest; duplicate must reject, never overwrite."""
        ...

    async def native_by_browser(self, digest: bytes) -> NativeAttempt | None: ...

    async def native_by_id(self, attempt_id: UUID) -> NativeAttempt | None: ...

    async def lock_native(self, attempt_id: UUID) -> NativeAttempt | None: ...

    async def bind_native(self, attempt_id: UUID, source_digest: bytes) -> None:
        """Called under row lock; persist only a digest of provisional credential."""
        ...

    async def limit_session_expiry(self, session_id: UUID, expires_at: datetime) -> None:
        """Shorten the provisional session to the handoff expiry, never extend it."""
        ...

    async def consume_native(self, attempt_id: UUID, at: datetime) -> None: ...

    async def cancel_native(self, attempt_id: UUID, at: datetime) -> None: ...

    async def add_session(self, session: Session, digest: bytes) -> None: ...


class NativeUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[NativeTransaction]: ...


def _require_live(attempt: NativeAttempt | None, now: datetime) -> NativeAttempt:
    if (
        attempt is None
        or attempt.consumed_at is not None
        or attempt.cancelled_at is not None
        or attempt.expires_at <= now
    ):
        raise NativeLoginRejectedError
    return attempt


@dataclass(frozen=True, slots=True)
class RegisterNativeAttempt:
    """After rate-limited BeginGoogleLogin; never expose its browser secret to JS."""

    unit_of_work: NativeUnitOfWork
    hasher: SessionHasher

    async def __call__(self, attempt_id: UUID, challenge: str, browser: SessionCredential) -> None:
        require_challenge(challenge)
        digest = await self.hasher.digest(browser)
        async with self.unit_of_work.transaction() as transaction:
            now = await transaction.now()
            await transaction.add_native(
                NativeAttempt(attempt_id, challenge, digest, now, now + NATIVE_LIFETIME)
            )


@dataclass(frozen=True, slots=True)
class BeginNativeLogin:
    google: BeginGoogleLogin
    register: RegisterNativeAttempt

    async def __call__(
        self,
        attempt_id: UUID,
        challenge: str,
        source_digest: bytes,
        previous_browser: SessionCredential | None = None,
    ) -> LoginStarted:
        require_challenge(challenge)
        started = await self.google(
            return_to="/onboarding", source_digest=source_digest, previous_browser=previous_browser
        )
        await self.register(attempt_id, challenge, started.browser)
        return started


@dataclass(frozen=True, slots=True)
class IdentifyNativeCallback:
    """Choose callback mode BEFORE normal completion, preserving browser web sessions."""

    unit_of_work: NativeUnitOfWork
    hasher: SessionHasher

    async def __call__(self, browser: SessionCredential | None) -> bool:
        if browser is None:
            return False
        digest = await self.hasher.digest(browser)
        async with self.unit_of_work.transaction() as transaction:
            return await transaction.native_by_browser(digest) is not None


@dataclass(frozen=True, slots=True)
class CancelNativeAttempt:
    unit_of_work: NativeUnitOfWork
    hasher: SessionHasher

    async def __call__(self, browser: SessionCredential) -> None:
        digest = await self.hasher.digest(browser)
        async with self.unit_of_work.transaction() as transaction:
            candidate = await transaction.native_by_browser(digest)
            if candidate is None:
                return
            attempt = await transaction.lock_native(candidate.id)
            if attempt is not None and attempt.consumed_at is None and attempt.cancelled_at is None:
                await transaction.cancel_native(attempt.id, await transaction.now())


@dataclass(frozen=True, slots=True)
class BindNativeCallback:
    """Run after existing Google callback succeeds, before any web cookie/redirect.

    True => native flow, discard provisional credential after commit, fixed wake URL.
    False => ordinary web callback unchanged. Invalid native flows must not fall back.
    """

    unit_of_work: NativeUnitOfWork
    hasher: SessionHasher

    async def __call__(self, browser: SessionCredential, credential: SessionCredential) -> bool:
        browser_digest = await self.hasher.digest(browser)
        source_digest = await self.hasher.digest(credential)
        async with self.unit_of_work.transaction() as transaction:
            candidate = await transaction.native_by_browser(browser_digest)
            if candidate is None:
                return False
            # Global order: identity/account + session, then native row. Exchange matches.
            try:
                identity, _ = await require_session_identity(transaction, source_digest)
            except UnauthenticatedError:
                raise NativeLoginRejectedError from None
            attempt = _require_live(
                await transaction.lock_native(candidate.id), await transaction.now()
            )
            if attempt.source_digest is not None or not hmac.compare_digest(
                attempt.browser_digest, browser_digest
            ):
                raise NativeLoginRejectedError
            await transaction.limit_session_expiry(identity.session.id, attempt.expires_at)
            await transaction.bind_native(attempt.id, source_digest)
        return True


@dataclass(frozen=True, slots=True)
class ExchangeNativeAttempt:
    unit_of_work: NativeUnitOfWork
    hasher: SessionHasher
    vault: LoginVault

    async def __call__(
        self,
        attempt_id: UUID,
        verifier: str,
        previous: SessionCredential | None = None,
    ) -> SessionCredential:
        expected = proof_challenge(verifier)
        async with self.unit_of_work.transaction() as transaction:
            candidate = _require_live(
                await transaction.native_by_id(attempt_id), await transaction.now()
            )
            if not hmac.compare_digest(candidate.challenge, expected):
                raise NativeLoginRejectedError
            if candidate.source_digest is None:
                raise NativeLoginPendingError
            try:
                identity, _ = await require_session_identity(transaction, candidate.source_digest)
            except UnauthenticatedError:
                raise NativeLoginRejectedError from None
            attempt = _require_live(
                await transaction.lock_native(attempt_id), await transaction.now()
            )
            if attempt.source_digest != candidate.source_digest or not hmac.compare_digest(
                attempt.challenge, expected
            ):
                raise NativeLoginRejectedError
            # Account replacement/deletion checked live; banned identities retain only
            # the same limited server-defined bootstrap authority as ordinary web login.
            # Never lock a second arbitrary actor while holding the first account lock.
            if previous is not None:
                previous_digest = await self.hasher.digest(previous)
                if previous_digest != candidate.source_digest:
                    raise NativeLoginRejectedError
            credential = await self.vault.session_credential()
            digest = await self.hasher.digest(credential)
            now = await transaction.now()
            _require_live(attempt, now)
            await transaction.add_session(
                Session(uuid4(), identity.session.account_id, now, now + SESSION_LIFETIME), digest
            )
            await transaction.revoke_session(identity.session.id, now)
            await transaction.consume_native(attempt.id, now)
        return credential


class GoogleCallbackCompletion(Protocol):
    async def __call__(self, command: GoogleCallbackCommand) -> LoginCompleted: ...


@dataclass(frozen=True, slots=True)
class NativeCallbackFinished:
    succeeded: bool


@dataclass(frozen=True, slots=True)
class CompleteLoginForClient:
    """One application callback boundary; ordinary web completion remains unchanged."""

    identify: IdentifyNativeCallback
    google: GoogleCallbackCompletion
    bind: BindNativeCallback
    cancel: CancelNativeAttempt

    async def __call__(
        self, command: GoogleCallbackCommand
    ) -> LoginCompleted | NativeCallbackFinished:
        if not await self.identify(command.browser):
            return await self.google(command)
        browser = command.browser
        if browser is None:
            raise NativeLoginRejectedError
        try:
            # The external browser's ordinary session is independent of the app.
            completed = await self.google(replace(command, previous=None))
            if not await self.bind(browser, completed.credential):
                raise NativeLoginRejectedError
        except (
            GoogleRejectedError,
            GoogleUnavailableError,
            CallbackRateLimitedError,
            NativeLoginRejectedError,
        ):
            await self.cancel(browser)
            return NativeCallbackFinished(succeeded=False)
        return NativeCallbackFinished(succeeded=True)
