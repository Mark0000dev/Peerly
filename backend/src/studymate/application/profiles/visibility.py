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
    SessionCredential,
    SessionHasher,
    StudentActionDeniedError,
    UnauthenticatedError,
    require_verified_student,
)
from studymate.application.profiles.onboarding import ProfileSetupReader
from studymate.domain.discovery_freshness import ExposureConfirmation
from studymate.domain.onboarding import ProfileLifecycle
from studymate.domain.profile_readiness import RestoreRequirement


class VisibilityVersionConflictError(Exception):
    def __init__(self, current_version: int) -> None:
        super().__init__("Profile visibility has changed")
        self.current_version = current_version


class ProfileRestoreIncompleteError(Exception):
    def __init__(self, requirements: tuple[RestoreRequirement, ...]) -> None:
        super().__init__("Profile restoration prerequisites are incomplete")
        self.requirements = requirements


@dataclass(frozen=True, slots=True)
class ChangeVisibilityCommand:
    credential: SessionCredential = field(repr=False)
    hidden: bool
    expected_version: int
    intent_key: IntentKey

    def __post_init__(self) -> None:
        if isinstance(self.expected_version, bool) or self.expected_version < 1:
            raise ValueError("Expected visibility revision must be positive")


@dataclass(frozen=True, slots=True)
class VisibilityIntent:
    fingerprint: bytes = field(repr=False)
    result_version: int
    exposure_confirmation: ExposureConfirmation | None = None


class VisibilityTransaction(ProfileSetupReader, Protocol):
    async def visibility_revision(self, account_id: UUID, version: int) -> ProfileLifecycle: ...

    async def visibility_intent(
        self, account_id: UUID, key: IntentKey
    ) -> VisibilityIntent | None: ...

    async def save_visibility(self, lifecycle: ProfileLifecycle) -> None: ...

    async def confirm_discovery_exposure(
        self,
        account_id: UUID,
        key: IntentKey,
        at: datetime,
    ) -> ExposureConfirmation | None: ...

    async def remember_visibility_intent(
        self, account_id: UUID, key: IntentKey, intent: VisibilityIntent, at: datetime
    ) -> None: ...


class VisibilityUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[VisibilityTransaction]: ...


@dataclass(frozen=True, slots=True)
class ChangeOwnVisibility:
    unit_of_work: VisibilityUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(self, command: ChangeVisibilityCommand) -> ProfileLifecycle:
        fingerprint = await self.fingerprinter.fingerprint(
            ("profile.visibility.v1", str(command.expected_version), str(command.hidden))
        )
        async with self.unit_of_work.transaction() as transaction:
            actor, _ = await require_verified_student(
                transaction, await self.hasher.digest(command.credential)
            )
            account_id = actor.session.account_id
            prior = await transaction.visibility_intent(account_id, command.intent_key)
            if prior is not None:
                if not hmac.compare_digest(prior.fingerprint, fingerprint):
                    raise IdempotencyConflictError
                return await transaction.visibility_revision(account_id, prior.result_version)
            snapshot = await transaction.setup_snapshot(account_id)
            lifecycle = snapshot.lifecycle
            if actor.registration is None or lifecycle is None:
                raise StudentActionDeniedError
            if lifecycle.visibility_version != command.expected_version:
                raise VisibilityVersionConflictError(lifecycle.visibility_version)
            state = snapshot.state()
            now = await transaction.now()
            exposure_paused = (
                snapshot.exposure.effective_pause(now) is not None
                if snapshot.exposure is not None
                else False
            )
            if (
                not command.hidden
                and (lifecycle.hidden or exposure_paused)
                and state.exposure_requirements
            ):
                raise ProfileRestoreIncompleteError(state.exposure_requirements)
            result = lifecycle.with_visibility(hidden=command.hidden, at=now)
            if result is not lifecycle:
                await transaction.save_visibility(result)
            confirmation = (
                await transaction.confirm_discovery_exposure(account_id, command.intent_key, now)
                if not command.hidden
                else None
            )
            await transaction.remember_visibility_intent(
                account_id,
                command.intent_key,
                VisibilityIntent(fingerprint, result.visibility_version, confirmation),
                now,
            )
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return result
