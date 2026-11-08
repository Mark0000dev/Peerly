import hmac
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from studymate.application.identity.google import (
    GoogleAuthorization,
    GoogleCode,
    GoogleProvider,
    GoogleRejectedError,
)
from studymate.application.identity.sessions import IdentityTransaction, SessionCredential
from studymate.domain.identity import Session
from studymate.domain.membership import GoogleIdentity

LOGIN_LIFETIME = timedelta(minutes=5)
SESSION_LIFETIME = timedelta(days=7)
MAX_STARTS_PER_HOUR = 30
MAX_CALLBACK_FAILURES_PER_HOUR = 30
RETURN_ROUTES = frozenset({"/", "/onboarding"})


class LoginCancelledError(GoogleRejectedError):
    """A validated browser login flow was declined."""


class LoginRateLimitedError(Exception):
    pass


class CallbackRateLimitedError(Exception):
    def __init__(self, retry_at: datetime) -> None:
        super().__init__("Callback failure budget exhausted")
        self.retry_at = retry_at


@dataclass(frozen=True, slots=True)
class CallbackBudget:
    used: int
    first_attempt_at: datetime | None


class AccountUnavailableError(GoogleRejectedError):
    """Retained deleted identity: no new account, session or automatic restore."""


@dataclass(frozen=True, slots=True)
class GoogleAccount:
    id: UUID
    deleted_at: datetime | None


@dataclass(frozen=True, slots=True)
class LoginMaterial:
    authorization: GoogleAuthorization = field(repr=False)
    browser: SessionCredential = field(repr=False)


@dataclass(frozen=True, slots=True)
class LoginFlow:
    id: UUID
    state_digest: bytes = field(repr=False)
    browser_digest: bytes = field(repr=False)
    sealed_material: bytes | None = field(repr=False)
    return_to: str
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class LoginStarted:
    redirect_url: str = field(repr=False)
    browser: SessionCredential = field(repr=False)


@dataclass(frozen=True, slots=True)
class LoginCompleted:
    credential: SessionCredential = field(repr=False)
    return_to: str


class LoginVault(Protocol):
    async def generate(self) -> LoginMaterial: ...

    async def session_credential(self) -> SessionCredential: ...

    async def digest(self, value: str) -> bytes: ...

    async def seal(self, material: GoogleAuthorization, flow_id: UUID) -> bytes: ...

    async def open(self, payload: bytes, flow_id: UUID) -> GoogleAuthorization: ...


class LoginTransaction(IdentityTransaction, Protocol):
    async def lock_callback_budget(
        self, source_digest: bytes, since: datetime
    ) -> CallbackBudget: ...

    async def add_callback_attempt(
        self, attempt_id: UUID, source_digest: bytes, at: datetime
    ) -> None: ...

    async def succeed_callback(self, attempt_id: UUID, account_id: UUID, at: datetime) -> None: ...

    async def lock_start_budget(self, source_digest: bytes, since: datetime) -> int: ...

    async def add_login(self, flow: LoginFlow, source_digest: bytes) -> None: ...

    async def invalidate_browser_flows(self, browser_digest: bytes, at: datetime) -> None: ...

    async def lock_login(self, state_digest: bytes) -> LoginFlow | None: ...

    async def lock_login_id(self, flow_id: UUID) -> LoginFlow | None: ...

    async def consume_login(self, flow_id: UUID, at: datetime) -> None: ...

    async def complete_login(self, flow_id: UUID, at: datetime) -> None: ...

    async def resolve_google(
        self, identity: GoogleIdentity, at: datetime, previous_digest: bytes | None = None
    ) -> GoogleAccount: ...

    async def add_session(self, session: Session, digest: bytes) -> None: ...


class LoginUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[LoginTransaction]: ...


@dataclass(frozen=True, slots=True)
class BeginGoogleLogin:
    unit_of_work: LoginUnitOfWork
    provider: GoogleProvider
    vault: LoginVault
    starts_per_hour: int = MAX_STARTS_PER_HOUR

    async def __call__(
        self,
        *,
        return_to: str,
        source_digest: bytes,
        previous_browser: SessionCredential | None = None,
    ) -> LoginStarted:
        if return_to not in RETURN_ROUTES:
            raise GoogleRejectedError
        material = await self.vault.generate()
        flow_id = uuid4()
        url = await self.provider.authorization_url(material.authorization)
        state_digest = await self.vault.digest(material.authorization.state)
        browser_digest = await self.vault.digest(material.browser.value)
        sealed = await self.vault.seal(material.authorization, flow_id)
        async with self.unit_of_work.transaction() as transaction:
            now = await transaction.now()
            used = await transaction.lock_start_budget(source_digest, now - timedelta(hours=1))
            if used >= self.starts_per_hour:
                raise LoginRateLimitedError
            if previous_browser is not None:
                await transaction.invalidate_browser_flows(
                    await self.vault.digest(previous_browser.value), now
                )
            await transaction.add_login(
                LoginFlow(
                    flow_id,
                    state_digest,
                    browser_digest,
                    sealed,
                    return_to,
                    now,
                    now + LOGIN_LIFETIME,
                ),
                source_digest,
            )
        return LoginStarted(url, material.browser)


@dataclass(frozen=True, slots=True)
class CompleteGoogleLogin:
    unit_of_work: LoginUnitOfWork
    provider: GoogleProvider
    vault: LoginVault

    async def __call__(
        self,
        *,
        state: str,
        browser: SessionCredential,
        code: GoogleCode | None,
        previous: SessionCredential | None = None,
        callback_attempt: UUID | None = None,
    ) -> LoginCompleted:
        state_digest = await self.vault.digest(state)
        browser_digest = await self.vault.digest(browser.value)
        async with self.unit_of_work.transaction() as transaction:
            flow = await transaction.lock_login(state_digest)
            now = await transaction.now()
            if (
                flow is None
                or flow.consumed_at is not None
                or flow.expires_at <= now
                or not hmac.compare_digest(flow.browser_digest, browser_digest)
                or flow.sealed_material is None
            ):
                raise GoogleRejectedError
            sealed = flow.sealed_material
            await transaction.consume_login(flow.id, now)
        if code is None:
            raise LoginCancelledError
        authorization = await self.vault.open(sealed, flow.id)
        identity = await self.provider.exchange(code, authorization)
        credential = await self.vault.session_credential()
        digest = await self.vault.digest(credential.value)
        async with self.unit_of_work.transaction() as transaction:
            claimed = await transaction.lock_login_id(flow.id)
            now = await transaction.now()
            if (
                claimed is None
                or claimed.consumed_at is None
                or claimed.completed_at is not None
                or claimed.expires_at <= now
            ):
                raise GoogleRejectedError
            previous_digest = (
                await self.vault.digest(previous.value) if previous is not None else None
            )
            account = await transaction.resolve_google(identity, now, previous_digest)
            if account.deleted_at is not None:
                raise AccountUnavailableError
            now = await transaction.now()
            if claimed.expires_at <= now:
                raise GoogleRejectedError
            if previous_digest is not None:
                old = await transaction.lock_identity(previous_digest)
                if old is not None and old.session.revoked_at is None:
                    await transaction.revoke_session(old.session.id, now)
            await transaction.add_session(
                Session(uuid4(), account.id, now, now + SESSION_LIFETIME),
                digest,
            )
            await transaction.complete_login(flow.id, now)
            if callback_attempt is not None:
                await transaction.succeed_callback(callback_attempt, account.id, now)
        return LoginCompleted(credential, flow.return_to)


@dataclass(frozen=True, slots=True)
class GoogleCallbackCommand:
    source_digest: bytes = field(repr=False)
    state: str = field(repr=False)
    browser: SessionCredential | None = field(repr=False)
    code: str | None = field(repr=False)
    malformed: bool = False
    cancelled: bool = False
    previous: SessionCredential | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class HandleGoogleCallback:
    """Reserve failure capacity before any validation or provider I/O.

    Failed, cancelled and interrupted attempts retain their slot. Successful
    callbacks release it atomically with session creation, never after delivery.
    """

    unit_of_work: LoginUnitOfWork
    complete: CompleteGoogleLogin
    failures_per_hour: int = MAX_CALLBACK_FAILURES_PER_HOUR

    async def __call__(self, command: GoogleCallbackCommand) -> LoginCompleted:
        attempt_id = uuid4()
        async with self.unit_of_work.transaction() as transaction:
            now = await transaction.now()
            budget = await transaction.lock_callback_budget(
                command.source_digest, now - timedelta(hours=1)
            )
            if budget.used >= self.failures_per_hour:
                raise CallbackRateLimitedError(
                    (budget.first_attempt_at or now) + timedelta(hours=1)
                )
            await transaction.add_callback_attempt(attempt_id, command.source_digest, now)
        if command.malformed or command.browser is None:
            raise GoogleRejectedError
        try:
            return await self.complete(
                state=command.state,
                browser=command.browser,
                code=GoogleCode(command.code) if command.code is not None else None,
                previous=command.previous,
                callback_attempt=attempt_id,
            )
        except LoginCancelledError:
            if command.cancelled:
                raise
            raise GoogleRejectedError from None
