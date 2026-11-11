import hmac
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID, uuid4

from studymate.application.idempotency import (
    IdempotencyConflictError,
    IntentFingerprinter,
    IntentKey,
)
from studymate.application.identity.sessions import (
    IdentityReader,
    SessionCredential,
    SessionHasher,
    StudentActionDeniedError,
    UnauthenticatedError,
    require_verified_student,
)
from studymate.domain.relationships import AccountPair, BlockRevision
from studymate.domain.reports import ProfileAccessContext
from studymate.domain.time import require_aware


class BlockTargetUnavailableError(Exception):
    pass


class BlockVersionConflictError(Exception):
    def __init__(self, current_version: int) -> None:
        super().__init__("Own block state has changed")
        self.current_version = current_version


@dataclass(frozen=True, slots=True)
class ChangeBlockCommand:
    credential: SessionCredential = field(repr=False)
    target_id: UUID
    blocked: bool
    expected_version: int
    intent_key: IntentKey
    context_id: UUID | None = None

    def __post_init__(self) -> None:
        if isinstance(self.expected_version, bool) or self.expected_version < 0:
            raise ValueError("Expected block revision must be nonnegative")


@dataclass(frozen=True, slots=True)
class OwnBlockResult:
    target_id: UUID
    blocked: bool
    version: int
    changed_at: datetime | None

    def __post_init__(self) -> None:
        if (
            isinstance(self.version, bool)
            or self.version < 0
            or (self.version == 0 and (self.blocked or self.changed_at is not None))
            or (self.version > 0 and self.changed_at is None)
        ):
            raise ValueError("Own block result must describe a real saved revision or absent block")
        if self.changed_at is not None:
            require_aware(self.changed_at)


@dataclass(frozen=True, slots=True)
class OwnBlockSnapshot:
    pair: AccountPair
    relationship_id: UUID | None
    own: BlockRevision | None

    def __post_init__(self) -> None:
        if self.own is not None and (
            self.own.relationship_id != self.relationship_id or self.own.pair != self.pair
        ):
            raise ValueError("Own block snapshot must belong to its canonical pair")


@dataclass(frozen=True, slots=True)
class BlockIntent:
    fingerprint: bytes = field(repr=False)
    result: OwnBlockResult
    context_id: UUID | None = None


class BlockTransaction(IdentityReader, Protocol):
    async def block_intent(self, actor_id: UUID, key: IntentKey) -> BlockIntent | None: ...

    async def current_own_block(self, actor_id: UUID, target_id: UUID) -> OwnBlockSnapshot: ...

    async def access_context(
        self, actor_id: UUID, context_id: UUID
    ) -> ProfileAccessContext | None: ...

    async def save_block(self, revision: BlockRevision) -> None: ...

    async def remember_block_intent(
        self,
        actor_id: UUID,
        key: IntentKey,
        intent: BlockIntent,
        at: datetime,
    ) -> None: ...


class BlockUnitOfWork(Protocol):
    def transaction(self, target_id: UUID) -> AbstractAsyncContextManager[BlockTransaction]: ...


async def _known_target(
    transaction: BlockTransaction,
    actor_id: UUID,
    command: ChangeBlockCommand,
    snapshot: OwnBlockSnapshot,
) -> None:
    if snapshot.pair != AccountPair.between(actor_id, command.target_id):
        raise RuntimeError("Block snapshot disagrees with scoped participants")
    if snapshot.own is not None:
        if snapshot.own.blocker_id != actor_id:
            raise RuntimeError("Own block snapshot belongs to another actor")
        if command.context_id is None:
            return
    context = (
        await transaction.access_context(actor_id, command.context_id)
        if command.context_id is not None
        else None
    )
    if (
        context is None
        or context.viewer_id != actor_id
        or context.snapshot.account_id != command.target_id
    ):
        raise BlockTargetUnavailableError


@dataclass(frozen=True, slots=True)
class ChangeOwnBlock:
    unit_of_work: BlockUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(self, command: ChangeBlockCommand) -> OwnBlockResult:
        fingerprint = await self.fingerprinter.fingerprint(
            (
                "block.change.v1",
                str(command.target_id),
                str(command.blocked),
                str(command.expected_version),
                str(command.context_id or ""),
            )
        )
        async with self.unit_of_work.transaction(command.target_id) as transaction:
            actor, _ = await require_verified_student(
                transaction, await self.hasher.digest(command.credential)
            )
            if not actor.activation_complete:
                raise StudentActionDeniedError
            actor_id = actor.session.account_id
            if actor_id == command.target_id:
                raise BlockTargetUnavailableError
            prior = await transaction.block_intent(actor_id, command.intent_key)
            if prior is not None:
                if not hmac.compare_digest(prior.fingerprint, fingerprint):
                    raise IdempotencyConflictError
                if prior.result.target_id != command.target_id:
                    raise RuntimeError("Saved block result belongs to another target")
                return prior.result
            snapshot = await transaction.current_own_block(actor_id, command.target_id)
            await _known_target(transaction, actor_id, command, snapshot)
            current = snapshot.own
            version = current.version if current is not None else 0
            if command.expected_version != version:
                raise BlockVersionConflictError(version)
            now = await transaction.now()
            result = OwnBlockResult(command.target_id, False, 0, None)
            if current is not None or command.blocked:
                revision = (
                    current.change(actor_id=actor_id, blocked=command.blocked, at=now)
                    if current is not None
                    else BlockRevision(
                        snapshot.relationship_id or uuid4(),
                        snapshot.pair,
                        actor_id,
                        1,
                        True,
                        now,
                    )
                )
                if revision is not current:
                    await transaction.save_block(revision)
                result = OwnBlockResult(
                    command.target_id, revision.blocked, revision.version, revision.changed_at
                )
            await transaction.remember_block_intent(
                actor_id,
                command.intent_key,
                BlockIntent(fingerprint, result, command.context_id),
                now,
            )
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return result
