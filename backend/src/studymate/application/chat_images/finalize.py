"""Queue an owned immutable image source; this never sends a chat message."""

import hmac
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from studymate.application.chat_images.start import ChatImageIntent, ChatImageMessageResolvedError
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
from studymate.application.messaging.ports import (
    ConversationAuthority,
    MessageContactUnavailableError,
)
from studymate.domain.chat_images import ChatImagePreparation, ChatImageState
from studymate.domain.messaging import MessageOperation


class ChatImageUnavailableError(Exception):
    """No image source exists within this actual participant's conversation."""


class ChatImageFinalizeTransaction(ConversationAuthority, Protocol):
    async def image_finalize_intent(
        self, actor_id: UUID, key: IntentKey
    ) -> ChatImageIntent | None: ...

    async def owned_image(
        self, actor_id: UUID, conversation_id: UUID, image_id: UUID
    ) -> ChatImagePreparation | None: ...

    async def message_operation(
        self, actor_id: UUID, conversation_id: UUID, client_message_id: UUID
    ) -> MessageOperation | None: ...

    async def save_image(self, image: ChatImagePreparation) -> None: ...

    async def remember_image_finalize(
        self, actor_id: UUID, key: IntentKey, intent: ChatImageIntent, at: datetime
    ) -> None: ...


class ChatImageFinalizeUnitOfWork(Protocol):
    def transaction(
        self, conversation_id: UUID
    ) -> AbstractAsyncContextManager[ChatImageFinalizeTransaction]: ...


@dataclass(frozen=True, slots=True)
class FinalizeChatImageCommand:
    credential: SessionCredential = field(repr=False)
    conversation_id: UUID
    image_id: UUID
    intent_key: IntentKey


def _owned(
    image: ChatImagePreparation, actor_id: UUID, command: FinalizeChatImageCommand
) -> ChatImagePreparation:
    if (image.account_id, image.conversation_id, image.id) != (
        actor_id,
        command.conversation_id,
        command.image_id,
    ):
        raise RuntimeError("Image finalization received an unrelated owned source")
    return image


@dataclass(frozen=True, slots=True)
class FinalizeChatImage:
    unit_of_work: ChatImageFinalizeUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(self, command: FinalizeChatImageCommand) -> ChatImagePreparation:
        async with self.unit_of_work.transaction(command.conversation_id) as transaction:
            actor, access = await authorize_conversation(
                transaction, self.hasher, command.credential, command.conversation_id
            )
            actor_id = actor.session.account_id
            digest = await self.fingerprinter.fingerprint(
                (
                    "chat.image.finalize.v1",
                    str(actor_id),
                    str(command.conversation_id),
                    str(command.image_id),
                )
            )
            prior = await transaction.image_finalize_intent(actor_id, command.intent_key)
            if prior is not None:
                if not hmac.compare_digest(prior.fingerprint, digest):
                    raise IdempotencyConflictError
                result = _owned(prior.result, actor_id, command)
            else:
                current = await transaction.owned_image(
                    actor_id, command.conversation_id, command.image_id
                )
                if current is None:
                    raise ChatImageUnavailableError
                current = _owned(current, actor_id, command)
                terminal = await transaction.message_operation(
                    actor_id, command.conversation_id, current.client_message_id
                )
                if terminal is not None:
                    if (
                        terminal.author_id,
                        terminal.conversation_id,
                        terminal.client_message_id,
                        terminal.pair,
                    ) != (
                        actor_id,
                        command.conversation_id,
                        current.client_message_id,
                        access.conversation.pair,
                    ):
                        raise RuntimeError(
                            "Image finalization received an unrelated message outcome"
                        )
                    raise ChatImageMessageResolvedError(terminal)
                now = await transaction.now()
                result = current.expire(now)
                if result.state == ChatImageState.UPLOADING:
                    if not access.can_send:
                        raise MessageContactUnavailableError
                    result = result.queue(now)
                if result is not current:
                    await transaction.save_image(result)
                await transaction.remember_image_finalize(
                    actor_id,
                    command.intent_key,
                    ChatImageIntent(digest, result),
                    await transaction.now(),
                )
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return result
