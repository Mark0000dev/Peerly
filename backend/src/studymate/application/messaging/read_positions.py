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
    SessionCredential,
    SessionHasher,
    UnauthenticatedError,
)
from studymate.application.messaging.commands import authorize_conversation
from studymate.application.messaging.ports import ConversationAccess, MessageTransaction
from studymate.domain.message_reads import ConversationReadPosition


class ReadSequenceUnavailableError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ReadPositionCommand:
    credential: SessionCredential = field(repr=False)
    conversation_id: UUID
    through_sequence: int
    key: IntentKey

    def __post_init__(self) -> None:
        if isinstance(self.through_sequence, bool) or self.through_sequence < 1:
            raise ValueError("Read acknowledgement requires a positive message sequence")


@dataclass(frozen=True, slots=True)
class ReadPositionIntent:
    fingerprint: bytes = field(repr=False)
    result: ConversationReadPosition


class ReadPositionTransaction(MessageTransaction, Protocol):
    async def read_position(
        self, actor_id: UUID, conversation_id: UUID
    ) -> ConversationReadPosition | None: ...

    async def read_position_intent(
        self, actor_id: UUID, key: IntentKey
    ) -> ReadPositionIntent | None: ...

    async def message_sequence_exists(self, conversation_id: UUID, sequence: int) -> bool: ...

    async def save_read_position(self, position: ConversationReadPosition) -> None:
        """Persist source-bound revision, current pointer and own canonical event atomically."""
        ...

    async def remember_read_position(
        self, actor_id: UUID, key: IntentKey, intent: ReadPositionIntent, at: datetime
    ) -> None: ...


class ReadPositionUnitOfWork(Protocol):
    def transaction(
        self, conversation_id: UUID
    ) -> AbstractAsyncContextManager[ReadPositionTransaction]: ...


def checked_read_position(
    position: ConversationReadPosition, access: ConversationAccess, actor_id: UUID
) -> ConversationReadPosition:
    if (
        position.conversation_id != access.conversation.id
        or position.account_id != actor_id
        or position.pair != access.conversation.pair
    ):
        raise RuntimeError("Private read position belongs to another participant scope")
    return position


@dataclass(frozen=True, slots=True)
class AcknowledgeConversationRead:
    unit_of_work: ReadPositionUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(self, command: ReadPositionCommand) -> ConversationReadPosition:
        async with self.unit_of_work.transaction(command.conversation_id) as transaction:
            actor, access = await authorize_conversation(
                transaction, self.hasher, command.credential, command.conversation_id
            )
            actor_id = actor.session.account_id
            fingerprint = await self.fingerprinter.fingerprint(
                (
                    "conversation.read.v1",
                    str(actor_id),
                    str(command.conversation_id),
                    str(command.through_sequence),
                )
            )
            prior = await transaction.read_position_intent(actor_id, command.key)
            if prior is not None:
                if not hmac.compare_digest(prior.fingerprint, fingerprint):
                    raise IdempotencyConflictError
                result = checked_read_position(prior.result, access, actor_id)
            else:
                if (
                    command.through_sequence >= access.conversation.next_message_sequence
                    or not await transaction.message_sequence_exists(
                        command.conversation_id, command.through_sequence
                    )
                ):
                    raise ReadSequenceUnavailableError
                current = await transaction.read_position(actor_id, command.conversation_id)
                if current is not None:
                    result = checked_read_position(current, access, actor_id).advance(
                        command.through_sequence, await transaction.now()
                    )
                else:
                    result = ConversationReadPosition(
                        uuid4(),
                        command.conversation_id,
                        access.conversation.pair,
                        actor_id,
                        1,
                        command.through_sequence,
                        await transaction.now(),
                    )
                if result != current:
                    await transaction.save_read_position(result)
                await transaction.remember_read_position(
                    actor_id,
                    command.key,
                    ReadPositionIntent(fingerprint, result),
                    await transaction.now(),
                )
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return result


@dataclass(frozen=True, slots=True)
class ReadConversationReadPosition:
    unit_of_work: ReadPositionUnitOfWork
    hasher: SessionHasher

    async def __call__(
        self, credential: SessionCredential, conversation_id: UUID
    ) -> ConversationReadPosition | None:
        async with self.unit_of_work.transaction(conversation_id) as transaction:
            actor, access = await authorize_conversation(
                transaction, self.hasher, credential, conversation_id
            )
            result = await transaction.read_position(actor.session.account_id, conversation_id)
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return (
                checked_read_position(result, access, actor.session.account_id)
                if result is not None
                else None
            )
