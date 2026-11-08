import hmac
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from studymate.application.idempotency import (
    IdempotencyConflictError,
    IntentFingerprinter,
    IntentKey,
)
from studymate.application.identity.sessions import (
    IdentitySnapshot,
    SessionCredential,
    SessionHasher,
    StudentActionDeniedError,
    UnauthenticatedError,
    require_verified_student,
)
from studymate.application.messaging.ports import (
    ClientMessageConflictError,
    ConversationAccess,
    ConversationAuthority,
    ConversationUnavailableError,
    MessageContactUnavailableError,
    MessageIntent,
    MessageTransaction,
    MessageUnitOfWork,
)
from studymate.domain.messaging import ConfirmedMessage, MessageContent, MessageOperation


@dataclass(frozen=True, slots=True)
class SendMessageCommand:
    credential: SessionCredential = field(repr=False)
    conversation_id: UUID
    client_message_id: UUID
    content: MessageContent = field(repr=False)
    intent_key: IntentKey


@dataclass(frozen=True, slots=True)
class CancelMessageCommand:
    credential: SessionCredential = field(repr=False)
    conversation_id: UUID
    client_message_id: UUID
    intent_key: IntentKey


async def authorize_conversation(
    transaction: ConversationAuthority,
    hasher: SessionHasher,
    credential: SessionCredential,
    conversation_id: UUID,
) -> tuple[IdentitySnapshot, ConversationAccess]:
    actor, _ = await require_verified_student(transaction, await hasher.digest(credential))
    if not actor.activation_complete:
        raise StudentActionDeniedError
    access = await transaction.conversation(actor.session.account_id, conversation_id)
    if access is None:
        raise ConversationUnavailableError
    if access.conversation.id != conversation_id or actor.session.account_id not in (
        access.conversation.pair.low,
        access.conversation.pair.high,
    ):
        raise RuntimeError("Conversation projection belongs to another participant scope")
    return actor, access


def _checked_operation(
    operation: MessageOperation,
    access: ConversationAccess,
    actor_id: UUID,
    client_message_id: UUID,
) -> MessageOperation:
    if (
        operation.conversation_id != access.conversation.id
        or operation.pair != access.conversation.pair
        or operation.author_id != actor_id
        or operation.client_message_id != client_message_id
    ):
        raise RuntimeError("Message outcome belongs to another operation scope")
    return operation


async def _prior(
    transaction: MessageTransaction,
    actor_id: UUID,
    name: str,
    key: IntentKey,
    fingerprint: bytes,
) -> MessageOperation | None:
    prior = await transaction.message_intent(actor_id, name, key)
    if prior is None:
        return None
    if not hmac.compare_digest(prior.fingerprint, fingerprint):
        raise IdempotencyConflictError
    return prior.operation


async def _remember(
    transaction: MessageTransaction,
    actor: IdentitySnapshot,
    name: str,
    key: IntentKey,
    intent: MessageIntent,
) -> None:
    await transaction.remember_message_intent(
        actor.session.account_id, name, key, intent, await transaction.now()
    )
    if not actor.session.is_active(await transaction.now()):
        raise UnauthenticatedError


@dataclass(frozen=True, slots=True)
class SendMessage:
    unit_of_work: MessageUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(self, command: SendMessageCommand) -> MessageOperation:
        async with self.unit_of_work.transaction(command.conversation_id) as transaction:
            actor, access = await authorize_conversation(
                transaction, self.hasher, command.credential, command.conversation_id
            )
            actor_id = actor.session.account_id
            digest = await self.fingerprinter.fingerprint(
                (
                    "chat.message.send.v1",
                    str(actor_id),
                    str(command.conversation_id),
                    str(command.client_message_id),
                    command.content.text or "",
                    str(command.content.image_id or ""),
                )
            )
            prior = await _prior(transaction, actor_id, "send", command.intent_key, digest)
            if prior is not None:
                if not actor.session.is_active(await transaction.now()):
                    raise UnauthenticatedError
                return _checked_operation(prior, access, actor_id, command.client_message_id)
            existing = await transaction.message_operation(
                actor_id, command.conversation_id, command.client_message_id
            )
            if existing is not None:
                result = _checked_operation(existing, access, actor_id, command.client_message_id)
                if result.message is not None and result.message.content != command.content:
                    raise ClientMessageConflictError
            else:
                if not access.can_send:
                    raise MessageContactUnavailableError
                await transaction.admit_message_content(
                    actor_id, command.conversation_id, command.client_message_id, command.content
                )
                at = await transaction.now()
                operation_id = uuid4()
                confirmed = ConfirmedMessage(
                    uuid4(),
                    operation_id,
                    command.conversation_id,
                    access.conversation.pair,
                    actor_id,
                    command.client_message_id,
                    access.conversation.next_message_sequence,
                    command.content,
                    at,
                )
                result = MessageOperation(
                    operation_id,
                    command.conversation_id,
                    access.conversation.pair,
                    actor_id,
                    command.client_message_id,
                    confirmed,
                )
                await transaction.save_message_operation(result)
            await _remember(
                transaction, actor, "send", command.intent_key, MessageIntent(digest, result)
            )
            return result


@dataclass(frozen=True, slots=True)
class CancelMessage:
    unit_of_work: MessageUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(self, command: CancelMessageCommand) -> MessageOperation:
        async with self.unit_of_work.transaction(command.conversation_id) as transaction:
            actor, access = await authorize_conversation(
                transaction, self.hasher, command.credential, command.conversation_id
            )
            actor_id = actor.session.account_id
            digest = await self.fingerprinter.fingerprint(
                (
                    "chat.message.cancel.v1",
                    str(actor_id),
                    str(command.conversation_id),
                    str(command.client_message_id),
                )
            )
            prior = await _prior(transaction, actor_id, "cancel", command.intent_key, digest)
            if prior is not None:
                if not actor.session.is_active(await transaction.now()):
                    raise UnauthenticatedError
                return _checked_operation(prior, access, actor_id, command.client_message_id)
            existing = await transaction.message_operation(
                actor_id, command.conversation_id, command.client_message_id
            )
            if existing is not None:
                result = _checked_operation(existing, access, actor_id, command.client_message_id)
            else:
                result = MessageOperation(
                    uuid4(),
                    command.conversation_id,
                    access.conversation.pair,
                    actor_id,
                    command.client_message_id,
                    cancelled_at=await transaction.now(),
                )
                await transaction.save_message_operation(result)
                await transaction.cancel_image_preparation(result)
            await _remember(
                transaction, actor, "cancel", command.intent_key, MessageIntent(digest, result)
            )
            return result


@dataclass(frozen=True, slots=True)
class ReadMessageOutcome:
    unit_of_work: MessageUnitOfWork
    hasher: SessionHasher

    async def __call__(
        self, credential: SessionCredential, conversation_id: UUID, client_message_id: UUID
    ) -> MessageOperation | None:
        async with self.unit_of_work.transaction(conversation_id) as transaction:
            actor, access = await authorize_conversation(
                transaction, self.hasher, credential, conversation_id
            )
            result = await transaction.message_operation(
                actor.session.account_id, conversation_id, client_message_id
            )
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            # None means unobserved, never a promise that a delayed Send cannot arrive.
            return (
                _checked_operation(result, access, actor.session.account_id, client_message_id)
                if result is not None
                else None
            )
