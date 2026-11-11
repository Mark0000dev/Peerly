from dataclasses import dataclass
from uuid import UUID

from studymate.application.idempotency import IntentFingerprinter, IntentKey
from studymate.application.identity.sessions import SessionCredential, SessionHasher
from studymate.application.requests.intents import remember, replay
from studymate.application.requests.ports import (
    AcceptedRequest,
    RequestIntent,
    RequestTransaction,
    RequestUnitOfWork,
    RequestVersionConflictError,
)
from studymate.application.requests.send import actor, finish
from studymate.application.requests.sources import eligible_sources
from studymate.domain.relationships import AccountPair
from studymate.domain.requests.states import ConnectionRequest, RequestUnavailableError


@dataclass(frozen=True, slots=True)
class RequestAction:
    credential: SessionCredential
    peer_id: UUID
    request_id: UUID
    expected_version: int
    key: IntentKey

    def __post_init__(self) -> None:
        if isinstance(self.expected_version, bool) or self.expected_version < 1:
            raise ValueError("Expected request revision must be positive")

    def fingerprint_parts(self, operation: str, actor_id: UUID) -> tuple[str, ...]:
        return (
            "requests.action.v1",
            operation,
            str(actor_id),
            str(self.peer_id),
            str(self.request_id),
            str(self.expected_version),
        )


async def load(
    transaction: RequestTransaction, actor_id: UUID, command: RequestAction
) -> ConnectionRequest:
    if actor_id == command.peer_id:
        raise RequestUnavailableError
    stored = await transaction.request(command.request_id)
    if stored is None or stored.pair != AccountPair.between(actor_id, command.peer_id):
        raise RequestUnavailableError
    if stored.version != command.expected_version:
        raise RequestVersionConflictError(stored.version)
    return stored.effective(await transaction.now())


async def save(
    transaction: RequestTransaction,
    actor_id: UUID,
    operation: str,
    command: RequestAction,
    intent: RequestIntent,
) -> None:
    if not isinstance(intent.result, (ConnectionRequest, AcceptedRequest)):
        raise RuntimeError("Decision needs an actual request result")
    request = intent.result.request if isinstance(intent.result, AcceptedRequest) else intent.result
    await transaction.save_request(request)
    await remember(transaction, actor_id, operation, command.key, intent)


@dataclass(frozen=True, slots=True)
class DeclineRequest:
    unit_of_work: RequestUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(self, command: RequestAction) -> ConnectionRequest:
        async with self.unit_of_work.transaction(command.peer_id) as transaction:
            identity = await actor(transaction, command.credential, self.hasher)
            actor_id = identity.session.account_id
            digest = await self.fingerprinter.fingerprint(
                command.fingerprint_parts("decline", actor_id)
            )
            prior = await replay(transaction, actor_id, "decline", command.key, digest)
            if prior is not None:
                if not isinstance(prior, ConnectionRequest):
                    raise RuntimeError("Stored decline has wrong result type")
                return prior
            current = await load(transaction, actor_id, command)
            result = current.decline(actor_id, await transaction.now())
            await save(transaction, actor_id, "decline", command, RequestIntent(digest, result))
            await finish(transaction, identity)
            return result


@dataclass(frozen=True, slots=True)
class UndoDecline:
    unit_of_work: RequestUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(self, command: RequestAction) -> ConnectionRequest:
        async with self.unit_of_work.transaction(command.peer_id) as transaction:
            identity = await actor(transaction, command.credential, self.hasher)
            actor_id = identity.session.account_id
            digest = await self.fingerprinter.fingerprint(
                command.fingerprint_parts("undo", actor_id)
            )
            prior = await replay(transaction, actor_id, "undo", command.key, digest)
            if prior is not None:
                if not isinstance(prior, ConnectionRequest):
                    raise RuntimeError("Stored Undo has wrong result type")
                return prior
            await eligible_sources(transaction, identity, command.peer_id)
            current = await load(transaction, actor_id, command)
            result = current.undo(actor_id, await transaction.now())
            await save(transaction, actor_id, "undo", command, RequestIntent(digest, result))
            await finish(transaction, identity)
            return result


@dataclass(frozen=True, slots=True)
class WithdrawRequest:
    unit_of_work: RequestUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(self, command: RequestAction) -> ConnectionRequest:
        async with self.unit_of_work.transaction(command.peer_id) as transaction:
            identity = await actor(transaction, command.credential, self.hasher)
            actor_id = identity.session.account_id
            digest = await self.fingerprinter.fingerprint(
                command.fingerprint_parts("withdraw", actor_id)
            )
            prior = await replay(transaction, actor_id, "withdraw", command.key, digest)
            if prior is not None:
                if not isinstance(prior, ConnectionRequest):
                    raise RuntimeError("Stored withdrawal has wrong result type")
                return prior
            current = await load(transaction, actor_id, command)
            result = current.withdraw(actor_id, await transaction.now())
            await save(transaction, actor_id, "withdraw", command, RequestIntent(digest, result))
            await finish(transaction, identity)
            return result


@dataclass(frozen=True, slots=True)
class AcceptRequest:
    unit_of_work: RequestUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(self, command: RequestAction) -> AcceptedRequest:
        async with self.unit_of_work.transaction(command.peer_id) as transaction:
            identity = await actor(transaction, command.credential, self.hasher)
            actor_id = identity.session.account_id
            digest = await self.fingerprinter.fingerprint(
                command.fingerprint_parts("accept", actor_id)
            )
            prior = await replay(transaction, actor_id, "accept", command.key, digest)
            if prior is not None:
                if not isinstance(prior, AcceptedRequest):
                    raise RuntimeError("Stored acceptance has wrong result type")
                return prior
            await eligible_sources(transaction, identity, command.peer_id)
            current = await load(transaction, actor_id, command)
            now = await transaction.now()
            # Validate role/state BEFORE invoking the real conversation foundation.
            if actor_id != current.context.recipient_id or current.state.value != "pending":
                raise RequestUnavailableError
            conversation = await transaction.create_conversation(current, now)
            if (
                conversation.relationship_id != current.relationship_id
                or conversation.pair != current.pair
                or conversation.request_id != current.id
            ):
                raise RuntimeError("Conversation foundation returned another request context")
            result = AcceptedRequest(
                current.accept(actor_id, conversation.id, await transaction.now()), conversation
            )
            await save(transaction, actor_id, "accept", command, RequestIntent(digest, result))
            await finish(transaction, identity)
            return result
