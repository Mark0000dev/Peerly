import hmac
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID, uuid4

from studymate.application.discovery.profiles import (
    DiscoveryProfileReader,
    DiscoveryProfileSource,
    DiscoveryProfileUnavailableError,
    authorize_discovery_profile,
    profile_declarations,
)
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
from studymate.domain.discovery import discovery_match
from studymate.domain.discovery_context import DiscoveryContext, DiscoveryScope, discovery_context
from studymate.domain.discovery_passes import PrivatePassRevision


class DiscoveryContextChangedError(Exception):
    pass


class PrivatePassConflictError(Exception):
    def __init__(self, current_version: int) -> None:
        super().__init__("Private pass state has changed")
        self.current_version = current_version


class PassUndoUnavailableError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ChangePassCommand:
    credential: SessionCredential = field(repr=False)
    context: DiscoveryScope
    target_id: UUID
    passed: bool
    expected_version: int
    intent_key: IntentKey
    undo: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.expected_version, bool) or self.expected_version < 0:
            raise ValueError("Expected private pass version must be nonnegative")
        if self.undo and self.passed:
            raise ValueError("Undo only reconsiders a private pass")


@dataclass(frozen=True, slots=True)
class PrivatePassIntent:
    fingerprint: bytes = field(repr=False)
    result: PrivatePassRevision


class PrivatePassTransaction(DiscoveryProfileReader, Protocol):
    async def pass_intent(self, actor_id: UUID, key: IntentKey) -> PrivatePassIntent | None: ...

    async def current_pass(
        self, context: DiscoveryContext, target_id: UUID
    ) -> PrivatePassRevision | None: ...

    async def latest_decision_sequence(self, actor_id: UUID) -> int: ...

    async def save_pass(self, revision: PrivatePassRevision) -> None: ...

    async def remember_pass_intent(
        self, actor_id: UUID, key: IntentKey, intent: PrivatePassIntent, at: datetime
    ) -> None: ...


class PrivatePassUnitOfWork(Protocol):
    def transaction(
        self, target_id: UUID
    ) -> AbstractAsyncContextManager[PrivatePassTransaction]: ...


async def _check_current_context(
    transaction: PrivatePassTransaction, context: DiscoveryContext
) -> DiscoveryProfileSource:
    source = await transaction.profile_source(context.account_id)
    if source is None or source.setup.account_id != context.account_id:
        raise DiscoveryContextChangedError
    current = discovery_context(
        context.account_id,
        context.mode,
        source.setup.goal.goal if source.setup.goal is not None else None,
        source.setup.help_subjects.revision if source.setup.help_subjects is not None else None,
    )
    if current != context:
        raise DiscoveryContextChangedError
    return source


def _updated_pass(
    command: ChangePassCommand,
    current: PrivatePassRevision | None,
    latest: int,
    now: datetime,
    context: DiscoveryContext,
) -> PrivatePassRevision:
    if current is None:
        if not command.passed:
            raise DiscoveryProfileUnavailableError
        return PrivatePassRevision(uuid4(), context, command.target_id, 1, True, latest + 1, now)
    if latest < current.decision_sequence:
        raise RuntimeError("Decision sequence precedes a retained private pass")
    if command.passed:
        return current.pass_again(latest + 1, now)
    return current.reconsider(latest + 1, now)


@dataclass(frozen=True, slots=True)
class ChangePrivatePass:
    unit_of_work: PrivatePassUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(self, command: ChangePassCommand) -> PrivatePassRevision:
        async with self.unit_of_work.transaction(command.target_id) as transaction:
            actor, _ = await require_verified_student(
                transaction, await self.hasher.digest(command.credential)
            )
            actor_id = actor.session.account_id
            if not actor.activation_complete:
                raise StudentActionDeniedError
            context = command.context.bind(actor_id)
            fingerprint = await self.fingerprinter.fingerprint(
                (
                    "discovery.pass.v1",
                    str(context.account_id),
                    context.mode.value,
                    str(context.goal_id or ""),
                    str(context.goal_version or ""),
                    str(context.help_version or ""),
                    str(command.target_id),
                    str(command.passed),
                    str(command.expected_version),
                    str(command.undo),
                )
            )
            if actor_id == command.target_id:
                raise DiscoveryProfileUnavailableError
            prior = await transaction.pass_intent(actor_id, command.intent_key)
            if prior is not None:
                if not hmac.compare_digest(prior.fingerprint, fingerprint):
                    raise IdempotencyConflictError
                if prior.result.context != context or prior.result.target_id != command.target_id:
                    raise RuntimeError("Private intent belongs to another decision scope")
                return prior.result
            own = await _check_current_context(transaction, context)
            current = await transaction.current_pass(context, command.target_id)
            if current is not None and (
                current.context != context or current.target_id != command.target_id
            ):
                raise RuntimeError("Private pass belongs to another decision scope")
            version = current.version if current is not None else 0
            if version != command.expected_version:
                raise PrivatePassConflictError(version)
            latest = await transaction.latest_decision_sequence(actor_id)
            if command.undo and (current is None or not current.can_undo(latest)):
                raise PassUndoUnavailableError
            if command.passed:
                _, target = await authorize_discovery_profile(
                    transaction, command.credential, self.hasher, command.target_id
                )
                if (
                    discovery_match(
                        profile_declarations(own), profile_declarations(target), context.mode
                    )
                    is None
                ):
                    raise DiscoveryProfileUnavailableError
            now = await transaction.now()
            result = _updated_pass(command, current, latest, now, context)
            if result is not current:
                await transaction.save_pass(result)
            await transaction.remember_pass_intent(
                actor_id, command.intent_key, PrivatePassIntent(fingerprint, result), now
            )
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return result
