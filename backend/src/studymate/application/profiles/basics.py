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
from studymate.domain.language_data import SUPPORTED_LANGUAGES
from studymate.domain.media import PhotoRevision
from studymate.domain.profiles import OnboardingTask, ProfileBasics, ProfileRevision


class ProfileNameRequiredError(Exception):
    pass


class UnsupportedProfileLanguageError(Exception):
    pass


class ProfileVersionConflictError(Exception):
    def __init__(self, current_version: int) -> None:
        super().__init__("Profile revision has changed")
        self.current_version = current_version


@dataclass(frozen=True, slots=True)
class SaveProfileCommand:
    credential: SessionCredential = field(repr=False)
    basics: ProfileBasics = field(repr=False)
    task: OnboardingTask
    expected_version: int
    intent_key: IntentKey

    def __post_init__(self) -> None:
        if isinstance(self.expected_version, bool) or self.expected_version < 0:
            raise ValueError("Expected profile version must be a nonnegative integer")


@dataclass(frozen=True, slots=True)
class ProfileIntent:
    fingerprint: bytes = field(repr=False)
    result_version: int


class ProfileTransaction(IdentityReader, Protocol):
    async def profile(
        self, account_id: UUID, version: int | None = None
    ) -> ProfileRevision | None: ...

    async def profile_intent(self, account_id: UUID, key: IntentKey) -> ProfileIntent | None: ...

    async def save_profile(self, revision: ProfileRevision) -> None: ...

    async def remember_profile_intent(
        self, account_id: UUID, key: IntentKey, intent: ProfileIntent, at: datetime
    ) -> None: ...


class ProfileUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[ProfileTransaction]: ...


def _profile_fingerprint_parts(command: SaveProfileCommand) -> tuple[str, ...]:
    basics = command.basics
    return (
        "profile.save.v1",
        str(command.expected_version),
        command.task.value,
        basics.display_name.value if basics.display_name is not None else "",
        basics.about or "",
        basics.programme or "",
        basics.year_label or "",
        *(language.value for language in basics.languages),
    )


@dataclass(frozen=True, slots=True)
class SaveOwnProfile:
    unit_of_work: ProfileUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(self, command: SaveProfileCommand) -> ProfileRevision:
        fingerprint = await self.fingerprinter.fingerprint(_profile_fingerprint_parts(command))
        async with self.unit_of_work.transaction() as transaction:
            actor, now = await require_verified_student(
                transaction, await self.hasher.digest(command.credential)
            )
            account_id = actor.session.account_id
            prior = await transaction.profile_intent(account_id, command.intent_key)
            if prior is not None:
                if not hmac.compare_digest(prior.fingerprint, fingerprint):
                    raise IdempotencyConflictError
                result = await transaction.profile(account_id, prior.result_version)
                if result is None:
                    raise RuntimeError("Saved profile result is unavailable")
                return result
            if any(
                language.value not in SUPPORTED_LANGUAGES for language in command.basics.languages
            ):
                raise UnsupportedProfileLanguageError
            if actor.activation_complete and command.basics.display_name is None:
                raise ProfileNameRequiredError
            current = await transaction.profile(account_id)
            version = current.version if current is not None else 0
            if command.expected_version != version:
                raise ProfileVersionConflictError(version)
            if (
                current is not None
                and current.basics == command.basics
                and current.task == command.task
            ):
                result = current
            else:
                result = ProfileRevision(account_id, version + 1, command.basics, command.task, now)
                await transaction.save_profile(result)
            await transaction.remember_profile_intent(
                account_id, command.intent_key, ProfileIntent(fingerprint, result.version), now
            )
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return result


class ProfileReadTransaction(IdentityReader, Protocol):
    async def profile(self, account_id: UUID) -> ProfileRevision | None: ...

    async def current_photo(self, account_id: UUID) -> PhotoRevision | None: ...


class ProfileReadUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[ProfileReadTransaction]: ...


@dataclass(frozen=True, slots=True)
class OwnProfileSnapshot:
    profile: ProfileRevision | None = field(repr=False)
    photo: PhotoRevision | None


@dataclass(frozen=True, slots=True)
class ReadOwnProfile:
    unit_of_work: ProfileReadUnitOfWork
    hasher: SessionHasher

    async def __call__(self, credential: SessionCredential) -> OwnProfileSnapshot:
        async with self.unit_of_work.transaction() as transaction:
            actor, _ = await require_verified_student(
                transaction, await self.hasher.digest(credential)
            )
            account_id = actor.session.account_id
            return OwnProfileSnapshot(
                await transaction.profile(account_id), await transaction.current_photo(account_id)
            )
