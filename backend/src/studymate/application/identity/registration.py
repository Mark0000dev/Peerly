from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import (
    IdentitySnapshot,
    IdentityTransaction,
    SessionCredential,
    SessionHasher,
    UnauthenticatedError,
    require_session_identity,
)
from studymate.application.profiles.onboarding import ProfileSetupSnapshot
from studymate.domain.onboarding import OnboardingActivation
from studymate.domain.profile_readiness import OnboardingRequirement
from studymate.domain.registration import (
    PolicyKind,
    PolicyReference,
    PolicyVersion,
    PublishedPolicy,
    RegistrationContext,
    RegistrationReceipt,
)

REGISTRATION_NOTICE = "By creating an account, you agree to our Terms of Use and Privacy Policy."
CONTEXT_LIFETIME = timedelta(minutes=10)


class RegistrationSetupIncompleteError(Exception):
    def __init__(self, requirements: tuple[OnboardingRequirement, ...]) -> None:
        super().__init__("Saved onboarding steps are incomplete")
        self.requirements = requirements


class RegistrationActionDeniedError(Exception):
    pass


class RegistrationAlreadyCompletedError(Exception):
    pass


class RegistrationContextUnavailableError(Exception):
    pass


class RegistrationDocumentsUnavailableError(Exception):
    pass


class PolicyDocumentUnavailableError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class RegistrationStatus:
    receipt: RegistrationReceipt | None
    current_terms: PolicyReference | None
    current_privacy: PolicyReference | None


@dataclass(frozen=True, slots=True)
class BeginRegistrationCommand:
    credential: SessionCredential = field(repr=False)
    intent_key: IntentKey


@dataclass(frozen=True, slots=True)
class CompleteRegistrationCommand:
    credential: SessionCredential = field(repr=False)
    context_id: UUID
    intent_key: IntentKey


class RegistrationTransaction(IdentityTransaction, Protocol):
    async def current_reference(self, kind: PolicyKind, at: datetime) -> PolicyReference | None: ...

    async def published_policy(
        self, kind: PolicyKind, version: PolicyVersion | None, at: datetime
    ) -> PublishedPolicy | None: ...

    async def context_by_key(
        self, account_id: UUID, key: IntentKey
    ) -> RegistrationContext | None: ...

    async def lock_context(self, context_id: UUID) -> RegistrationContext | None: ...

    async def add_context(self, context: RegistrationContext, key: IntentKey) -> None: ...

    async def record_completion(self, receipt: RegistrationReceipt) -> None: ...

    async def setup_snapshot(self, account_id: UUID) -> ProfileSetupSnapshot: ...

    async def activate_profile(self, activation: OnboardingActivation) -> None: ...


class RegistrationUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[RegistrationTransaction]: ...


async def _registrant(
    transaction: RegistrationTransaction, digest: bytes
) -> tuple[IdentitySnapshot, datetime]:
    actor, now = await require_session_identity(transaction, digest)
    if actor.banned or actor.membership is None or not actor.membership.is_verified:
        raise RegistrationActionDeniedError
    return actor, now


@dataclass(frozen=True, slots=True)
class BeginRegistration:
    unit_of_work: RegistrationUnitOfWork
    hasher: SessionHasher

    async def __call__(self, command: BeginRegistrationCommand) -> RegistrationContext:
        digest = await self.hasher.digest(command.credential)
        async with self.unit_of_work.transaction() as transaction:
            actor, now = await _registrant(transaction, digest)
            account_id = actor.session.account_id
            if actor.registration is not None:
                raise RegistrationAlreadyCompletedError
            prior = await transaction.context_by_key(account_id, command.intent_key)
            if prior is not None:
                if prior.session_id != actor.session.id:
                    raise IdempotencyConflictError
                return prior
            terms = await transaction.current_reference(PolicyKind.TERMS, now)
            privacy = await transaction.current_reference(PolicyKind.PRIVACY, now)
            if terms is None or privacy is None:
                raise RegistrationDocumentsUnavailableError
            context = RegistrationContext(
                uuid4(),
                account_id,
                actor.session.id,
                terms,
                privacy,
                REGISTRATION_NOTICE,
                now,
                now + CONTEXT_LIFETIME,
            )
            await transaction.add_context(context, command.intent_key)
            return context


async def _activate_profile(
    transaction: RegistrationTransaction, actor: IdentitySnapshot, receipt: RegistrationReceipt
) -> None:
    snapshot = await transaction.setup_snapshot(actor.session.account_id)
    if snapshot.lifecycle is not None:
        return
    requirements = snapshot.state().initial_requirements
    if requirements:
        raise RegistrationSetupIncompleteError(requirements)
    # Explicit narrowing also protects the domain construction from inconsistent adapters.
    if snapshot.profile is None or snapshot.photo is None:
        raise ValueError("Ready setup must contain its saved profile and photo")
    now = await transaction.now()
    if not actor.session.is_active(now):
        raise UnauthenticatedError
    await transaction.activate_profile(
        OnboardingActivation(
            snapshot.profile,
            snapshot.photo,
            snapshot.goal.goal if snapshot.goal is not None else None,
            snapshot.help_subjects.revision if snapshot.help_subjects is not None else None,
            receipt,
            now,
        )
    )


@dataclass(frozen=True, slots=True)
class CompleteRegistration:
    unit_of_work: RegistrationUnitOfWork
    hasher: SessionHasher

    async def __call__(self, command: CompleteRegistrationCommand) -> RegistrationReceipt:
        digest = await self.hasher.digest(command.credential)
        async with self.unit_of_work.transaction() as transaction:
            actor, _ = await _registrant(transaction, digest)
            account_id = actor.session.account_id
            prior = actor.registration
            if prior is not None:
                if (
                    prior.intent_key == command.intent_key.value
                    and prior.context.id != command.context_id
                ):
                    raise IdempotencyConflictError
                await _activate_profile(transaction, actor, prior)
                return prior
            context = await transaction.lock_context(command.context_id)
            now = await transaction.now()
            if context is None or not context.can_complete(account_id, actor.session.id, now):
                raise RegistrationContextUnavailableError
            if not actor.session.is_active(now):
                raise UnauthenticatedError
            completed = context.complete(account_id, actor.session.id, now)
            receipt = RegistrationReceipt(
                uuid4(), account_id, completed, now, command.intent_key.value
            )
            await transaction.record_completion(receipt)
            await _activate_profile(transaction, actor, receipt)
            return receipt


@dataclass(frozen=True, slots=True)
class ReadPolicyStatus:
    unit_of_work: RegistrationUnitOfWork
    hasher: SessionHasher

    async def __call__(self, credential: SessionCredential) -> RegistrationStatus:
        async with self.unit_of_work.transaction() as transaction:
            actor, now = await require_session_identity(
                transaction, await self.hasher.digest(credential)
            )
            return RegistrationStatus(
                actor.registration,
                await transaction.current_reference(PolicyKind.TERMS, now),
                await transaction.current_reference(PolicyKind.PRIVACY, now),
            )


@dataclass(frozen=True, slots=True)
class ReadPublishedPolicy:
    unit_of_work: RegistrationUnitOfWork

    async def __call__(
        self, kind: PolicyKind, version: PolicyVersion | None = None
    ) -> PublishedPolicy:
        async with self.unit_of_work.transaction() as transaction:
            document = await transaction.published_policy(kind, version, await transaction.now())
            if document is None:
                raise PolicyDocumentUnavailableError
            return document
