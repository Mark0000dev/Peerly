import hmac
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from studymate.application.idempotency import (
    IdempotencyConflictError,
    IntentFingerprinter,
    IntentKey,
)
from studymate.application.identity.sessions import (
    IdentityReader,
    IdentitySnapshot,
    IdentityTransaction,
    Logout,
    SessionCredential,
    SessionHasher,
    UnauthenticatedError,
    require_verified_student,
)
from studymate.domain.student_notifications.capabilities import (
    Capabilities,
    DeviceState,
    Registration,
)


class DeliveryUnavailableError(Exception):
    pass


class SubscriptionVersionError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class SubscriptionIntent:
    fingerprint: bytes = field(repr=False)
    result: DeviceState


class SubscriptionTransaction(IdentityReader, Protocol):
    async def read(self, account_id: UUID, installation: UUID) -> DeviceState | None: ...

    async def replay(self, account_id: UUID, key: IntentKey) -> SubscriptionIntent | None: ...

    async def save(
        self,
        account_id: UUID,
        session_id: UUID,
        value: Registration,
        prior: DeviceState | None,
    ) -> DeviceState: ...

    async def remember(
        self, account_id: UUID, key: IntentKey, intent: SubscriptionIntent
    ) -> None: ...


class SubscriptionUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[SubscriptionTransaction]: ...


@dataclass(frozen=True, slots=True)
class RegisterDeviceCommand:
    credential: SessionCredential = field(repr=False)
    registration: Registration
    expected_version: int
    intent_key: IntentKey

    def __post_init__(self) -> None:
        if isinstance(self.expected_version, bool) or self.expected_version < 0:
            raise ValueError("Nonnegative subscription version required")


@dataclass(frozen=True, slots=True)
class RegisterOwnDelivery:
    unit: SubscriptionUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter
    capabilities: Capabilities

    async def __call__(self, command: RegisterDeviceCommand) -> DeviceState:
        value = command.registration
        fingerprint = await self.fingerprinter.fingerprint(
            (
                "notification.subscription.v1",
                str(value.installation_id),
                value.platform.value,
                str(value.enabled),
                value.timezone or "",
                value.endpoint or "",
                value.p256dh or "",
                value.auth or "",
                str(command.expected_version),
            )
        )
        async with self.unit.transaction() as transaction:
            identity, _ = await require_verified_student(
                transaction, await self.hasher.digest(command.credential)
            )
            owner = identity.session.account_id
            replay = await transaction.replay(owner, command.intent_key)
            if replay is not None:
                if not hmac.compare_digest(replay.fingerprint, fingerprint):
                    raise IdempotencyConflictError
                if not identity.session.is_active(await transaction.now()):
                    raise UnauthenticatedError
                return replay.result
            if value.enabled and not self.capabilities.supports(value.platform):
                raise DeliveryUnavailableError
            prior = await transaction.read(owner, value.installation_id)
            if (0 if prior is None else prior.version) != command.expected_version:
                raise SubscriptionVersionError
            result = await transaction.save(owner, identity.session.id, value, prior)
            await transaction.remember(
                owner, command.intent_key, SubscriptionIntent(fingerprint, result)
            )
            if not identity.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return result


class RetirementDisposition(StrEnum):
    RETIRED = "retired"
    UNCONFIRMED = "unconfirmed"


class InstallationLogoutTransaction(IdentityTransaction, Protocol):
    async def retire_installation(
        self,
        account_id: UUID,
        session_id: UUID,
        installation_id: UUID | None,
        at: datetime,
    ) -> bool: ...


class InstallationLogoutUnitOfWork(Protocol):
    def transaction(
        self,
    ) -> AbstractAsyncContextManager[InstallationLogoutTransaction]: ...


@dataclass(slots=True)
class _InstallationLogoutTransaction:
    """Decorate canonical Logout's revoke step; never duplicate its auth/revoke policy."""

    transaction: InstallationLogoutTransaction
    installation_id: UUID | None
    identity: IdentitySnapshot | None = None
    disposition: RetirementDisposition = RetirementDisposition.UNCONFIRMED

    def authenticated(self, account_id: UUID) -> None:
        self.transaction.authenticated(account_id)

    async def lock_identity(self, secret_digest: bytes) -> IdentitySnapshot | None:
        self.identity = await self.transaction.lock_identity(secret_digest)
        return self.identity

    async def now(self) -> datetime:
        return await self.transaction.now()

    async def revoke_session(self, session_id: UUID, at: datetime) -> None:
        identity = self.identity
        if (
            identity is not None
            and identity.session.id == session_id
            and identity.deleted_at is None
            and identity.session.is_active(at)
        ):
            retired = await self.transaction.retire_installation(
                identity.session.account_id, session_id, self.installation_id, at
            )
            if retired:
                self.disposition = RetirementDisposition.RETIRED
        await self.transaction.revoke_session(session_id, at)


@dataclass(frozen=True, slots=True)
class _BoundLogoutUnit:
    transaction_value: _InstallationLogoutTransaction

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[IdentityTransaction]:
        # Commit/rollback belongs to the outer notification UoW, including revocation.
        yield self.transaction_value


@dataclass(frozen=True, slots=True)
class LogoutInstallation:
    unit: InstallationLogoutUnitOfWork
    hasher: SessionHasher

    async def __call__(
        self, credential: SessionCredential, installation_id: UUID | None = None
    ) -> RetirementDisposition:
        async with self.unit.transaction() as transaction:
            decorated = _InstallationLogoutTransaction(transaction, installation_id)
            await Logout(_BoundLogoutUnit(decorated), self.hasher)(credential)
        return decorated.disposition
