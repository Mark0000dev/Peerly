"""Admit one exact image source for an actual accepted message intent."""

import hmac
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
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
from studymate.application.media.uploads import UploadBudget
from studymate.application.messaging.commands import authorize_conversation
from studymate.application.messaging.ports import (
    ConversationAuthority,
    MessageContactUnavailableError,
)
from studymate.domain.chat_images import ChatImagePreparation
from studymate.domain.media import PhotoSource
from studymate.domain.messaging import MessageOperation

UPLOAD_LIFETIME = timedelta(minutes=15)
PROCESSING_LIFETIME = timedelta(hours=1)
STARTS_PER_HOUR = 20
PENDING_LIMIT = 3


class ChatImageSourceConflictError(Exception):
    """An existing client-message identity is already bound to different source bytes."""


class ChatImageMessageResolvedError(Exception):
    def __init__(self, operation: MessageOperation) -> None:
        super().__init__("The actual message intent already has a terminal outcome")
        self.operation = operation


class ChatImageRateLimitedError(Exception):
    def __init__(self, retry_at: datetime) -> None:
        super().__init__("Chat image preparation capacity is exhausted")
        self.retry_at = retry_at


@dataclass(frozen=True, slots=True)
class ChatImageIntent:
    fingerprint: bytes = field(repr=False)
    result: ChatImagePreparation = field(repr=False)


class ChatImageStartTransaction(ConversationAuthority, Protocol):
    async def image_start_intent(
        self, actor_id: UUID, key: IntentKey
    ) -> ChatImageIntent | None: ...

    async def message_operation(
        self, actor_id: UUID, conversation_id: UUID, client_message_id: UUID
    ) -> MessageOperation | None: ...

    async def client_image(
        self, actor_id: UUID, conversation_id: UUID, client_message_id: UUID
    ) -> ChatImagePreparation | None: ...

    async def expire_pending_images(self, actor_id: UUID, at: datetime) -> None: ...

    async def image_budget(self, actor_id: UUID, since: datetime) -> UploadBudget: ...

    async def create_image(self, image: ChatImagePreparation) -> None: ...

    async def remember_image_start(
        self, actor_id: UUID, key: IntentKey, intent: ChatImageIntent, at: datetime
    ) -> None: ...


class ChatImageStartUnitOfWork(Protocol):
    def transaction(
        self, conversation_id: UUID
    ) -> AbstractAsyncContextManager[ChatImageStartTransaction]: ...


@dataclass(frozen=True, slots=True)
class StartChatImageCommand:
    credential: SessionCredential = field(repr=False)
    conversation_id: UUID
    client_message_id: UUID
    source: PhotoSource = field(repr=False)
    intent_key: IntentKey


def _capacity_retry(budget: UploadBudget, now: datetime) -> datetime | None:
    waits: list[datetime] = []
    if budget.starts >= STARTS_PER_HOUR:
        if budget.first_start_at is None:
            raise RuntimeError("Image start capacity lost its actual retained source")
        waits.append(budget.first_start_at + timedelta(hours=1))
    if budget.pending >= PENDING_LIMIT:
        if budget.next_pending_expiry is None:
            raise RuntimeError("Pending image capacity lost its actual deadline")
        waits.append(budget.next_pending_expiry)
    if waits and min(waits) <= now:
        raise RuntimeError("Expired image capacity must be reconciled before admission")
    return max(waits) if waits else None


def _owned(
    image: ChatImagePreparation, actor_id: UUID, command: StartChatImageCommand
) -> ChatImagePreparation:
    if (image.account_id, image.conversation_id, image.client_message_id) != (
        actor_id,
        command.conversation_id,
        command.client_message_id,
    ):
        raise RuntimeError("Image preparation projection belongs to another message intent")
    if image.source != command.source:
        raise ChatImageSourceConflictError
    return image


@dataclass(frozen=True, slots=True)
class StartChatImage:
    unit_of_work: ChatImageStartUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(self, command: StartChatImageCommand) -> ChatImagePreparation:
        async with self.unit_of_work.transaction(command.conversation_id) as transaction:
            actor, access = await authorize_conversation(
                transaction, self.hasher, command.credential, command.conversation_id
            )
            actor_id = actor.session.account_id
            digest = await self.fingerprinter.fingerprint(
                (
                    "chat.image.start.v1",
                    str(actor_id),
                    str(command.conversation_id),
                    str(command.client_message_id),
                    str(command.source.size),
                    command.source.content_type.value,
                    command.source.sha256.hex(),
                )
            )
            prior = await transaction.image_start_intent(actor_id, command.intent_key)
            if prior is not None:
                if not hmac.compare_digest(prior.fingerprint, digest):
                    raise IdempotencyConflictError
                result = _owned(prior.result, actor_id, command)
            else:
                terminal = await transaction.message_operation(
                    actor_id, command.conversation_id, command.client_message_id
                )
                if terminal is not None:
                    if (
                        terminal.author_id,
                        terminal.conversation_id,
                        terminal.client_message_id,
                    ) != (
                        actor_id,
                        command.conversation_id,
                        command.client_message_id,
                    ) or terminal.pair != access.conversation.pair:
                        raise RuntimeError("Image admission received an unrelated message outcome")
                    raise ChatImageMessageResolvedError(terminal)
                existing = await transaction.client_image(
                    actor_id, command.conversation_id, command.client_message_id
                )
                if existing is not None:
                    result = _owned(existing, actor_id, command)
                else:
                    if not access.can_send:
                        raise MessageContactUnavailableError
                    now = await transaction.now()
                    await transaction.expire_pending_images(actor_id, now)
                    budget = await transaction.image_budget(actor_id, now - timedelta(hours=1))
                    retry = _capacity_retry(budget, now)
                    if retry is not None:
                        raise ChatImageRateLimitedError(retry)
                    result = ChatImagePreparation(
                        uuid4(),
                        actor_id,
                        command.conversation_id,
                        command.client_message_id,
                        command.source,
                        now,
                        now + UPLOAD_LIFETIME,
                        now + PROCESSING_LIFETIME,
                        now,
                    )
                    await transaction.create_image(result)
                await transaction.remember_image_start(
                    actor_id,
                    command.intent_key,
                    ChatImageIntent(digest, result),
                    await transaction.now(),
                )
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return result
