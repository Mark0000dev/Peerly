import hmac
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from studymate.application.idempotency import (
    IdempotencyConflictError,
    IntentFingerprinter,
    IntentKey,
)
from studymate.application.identity.sessions import (
    IdentityReader,
    SessionCredential,
    SessionHasher,
    UnauthenticatedError,
    require_verified_student,
)
from studymate.domain.notification_preferences.state import NotificationMode, NotificationPreference


class PreferenceVersionConflictError(Exception):
    def __init__(self, current_version: int) -> None:
        super().__init__("Notification preference has changed")
        self.current_version = current_version


@dataclass(frozen=True, slots=True)
class PreferenceIntent:
    fingerprint: bytes = field(repr=False)
    result: NotificationPreference


@dataclass(frozen=True, slots=True)
class ChoosePreferenceCommand:
    credential: SessionCredential = field(repr=False)
    mode: NotificationMode
    expected_version: int
    intent_key: IntentKey

    def __post_init__(self) -> None:
        if isinstance(self.expected_version, bool) or self.expected_version < 0:
            raise ValueError("Expected preference version must be nonnegative")


class PreferenceTransaction(IdentityReader, Protocol):
    async def preference(self, account_id: UUID) -> NotificationPreference: ...

    async def intent(self, account_id: UUID, key: IntentKey) -> PreferenceIntent | None: ...

    async def save(self, account_id: UUID, result: NotificationPreference) -> None: ...

    async def remember(
        self, account_id: UUID, key: IntentKey, intent: PreferenceIntent, at: datetime
    ) -> None: ...


class PreferenceUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[PreferenceTransaction]: ...


@dataclass(frozen=True, slots=True)
class ReadOwnNotificationPreference:
    unit_of_work: PreferenceUnitOfWork
    hasher: SessionHasher

    async def __call__(self, credential: SessionCredential) -> NotificationPreference:
        async with self.unit_of_work.transaction() as transaction:
            identity, _ = await require_verified_student(
                transaction, await self.hasher.digest(credential)
            )
            return await transaction.preference(identity.session.account_id)


@dataclass(frozen=True, slots=True)
class ChooseOwnNotificationPreference:
    unit_of_work: PreferenceUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(self, command: ChoosePreferenceCommand) -> NotificationPreference:
        fingerprint = await self.fingerprinter.fingerprint(
            ("notification.preference.v1", command.mode.value, str(command.expected_version))
        )
        async with self.unit_of_work.transaction() as transaction:
            identity, now = await require_verified_student(
                transaction, await self.hasher.digest(command.credential)
            )
            owner = identity.session.account_id
            prior = await transaction.intent(owner, command.intent_key)
            if prior is not None:
                if not hmac.compare_digest(prior.fingerprint, fingerprint):
                    raise IdempotencyConflictError
                result = prior.result
            else:
                current = await transaction.preference(owner)
                if current.version != command.expected_version:
                    raise PreferenceVersionConflictError(current.version)
                result = current.choose(command.mode, now)
                if result is not current:
                    await transaction.save(owner, result)
                await transaction.remember(
                    owner, command.intent_key, PreferenceIntent(fingerprint, result), now
                )
            if not identity.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return result
