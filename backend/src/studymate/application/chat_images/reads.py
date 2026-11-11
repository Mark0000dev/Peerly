"""Owned reload projections: retained source state is distinct from effective expiry."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from studymate.application.chat_images.finalize import ChatImageUnavailableError
from studymate.application.identity.sessions import (
    SessionCredential,
    SessionHasher,
    UnauthenticatedError,
)
from studymate.application.messaging.commands import authorize_conversation
from studymate.application.messaging.ports import ConversationAuthority
from studymate.domain.chat_images import ChatImagePreparation, ChatImageState
from studymate.domain.messaging import MessageOutcome
from studymate.domain.relationships import AccountPair
from studymate.domain.time import require_aware

MAX_DISPLAY_DIMENSION = 1024
PENDING_IMAGE_LIMIT = 3
TERMINAL_IMAGE_LIMIT = 20
OWNED_IMAGE_LIMIT = PENDING_IMAGE_LIMIT + TERMINAL_IMAGE_LIMIT


@dataclass(frozen=True, slots=True)
class ReadyImageInfo:
    attempt_id: UUID
    width: int
    height: int
    size: int

    def __post_init__(self) -> None:
        if (
            not 1 <= self.width <= MAX_DISPLAY_DIMENSION
            or not 1 <= self.height <= MAX_DISPLAY_DIMENSION
            or self.size < 1
        ):
            raise ValueError("Ready image requires actual bounded display metadata")


@dataclass(frozen=True, slots=True)
class ImageMessageOutcome:
    """An actual logical message outcome, not evidence of a particular attachment."""

    id: UUID
    pair: AccountPair
    account_id: UUID
    conversation_id: UUID
    client_message_id: UUID
    outcome: MessageOutcome
    message_id: UUID | None
    message_image_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.account_id not in (self.pair.low, self.pair.high):
            raise ValueError("Image message outcome requires an actual participant")
        if (self.outcome == MessageOutcome.CONFIRMED) != (self.message_id is not None):
            raise ValueError("Image message outcome lost its actual confirmed message identifier")
        if self.outcome == MessageOutcome.CANCELLED and self.message_image_id is not None:
            raise ValueError("Cancelled message outcome cannot have an actual attachment")


@dataclass(frozen=True, slots=True)
class ImagePreparationSource:
    preparation: ChatImagePreparation
    ready: ReadyImageInfo | None = None
    message_outcome: ImageMessageOutcome | None = None


@dataclass(frozen=True, slots=True)
class OwnedImagePreparation:
    preparation: ChatImagePreparation
    effective_state: ChatImageState
    ready: ReadyImageInfo | None
    message_outcome: ImageMessageOutcome | None


class ImageReadTransaction(ConversationAuthority, Protocol):
    async def image_source(
        self, account_id: UUID, conversation_id: UUID, image_id: UUID
    ) -> ImagePreparationSource | None: ...

    async def image_sources(
        self, account_id: UUID, conversation_id: UUID
    ) -> tuple[ImagePreparationSource, ...]: ...


class ImageReadUnitOfWork(Protocol):
    def transaction(
        self, conversation_id: UUID
    ) -> AbstractAsyncContextManager[ImageReadTransaction]: ...


def owned_value(
    source: ImagePreparationSource,
    account_id: UUID,
    conversation_id: UUID,
    pair: AccountPair,
    at: datetime,
) -> OwnedImagePreparation:
    require_aware(at)
    image = source.preparation
    if (image.account_id, image.conversation_id) != (account_id, conversation_id):
        raise RuntimeError("Image read returned another actual owner/conversation")
    if at < image.updated_at:
        raise RuntimeError("Image projection precedes its actual retained source revision")
    if (source.ready is not None) != (image.state == ChatImageState.READY) or (
        source.ready is not None and source.ready.attempt_id != image.attempt_id
    ):
        raise RuntimeError("Ready display metadata differs from its actual owned attempt")
    outcome = source.message_outcome
    if outcome is not None and (
        outcome.account_id,
        outcome.conversation_id,
        outcome.client_message_id,
        outcome.pair,
    ) != (account_id, conversation_id, image.client_message_id, pair):
        raise RuntimeError("Image read returned another actual logical message outcome")
    if (
        outcome is not None
        and outcome.message_image_id is not None
        and outcome.message_image_id != image.id
    ):
        raise RuntimeError("Image read attachment differs from its actual preparation source")
    deadline = (
        image.upload_expires_at
        if image.state == ChatImageState.UPLOADING
        else image.processing_expires_at
    )
    effective = ChatImageState.EXPIRED if image.pending and at >= deadline else image.state
    # Never call image.expire(): that would invent a new persisted-looking revision.
    return OwnedImagePreparation(image, effective, source.ready, outcome)


@dataclass(frozen=True, slots=True)
class ReadOwnedImagePreparation:
    unit_of_work: ImageReadUnitOfWork
    hasher: SessionHasher

    async def __call__(
        self,
        credential: SessionCredential,
        conversation_id: UUID,
        image_id: UUID,
    ) -> OwnedImagePreparation:
        async with self.unit_of_work.transaction(conversation_id) as tx:
            actor, access = await authorize_conversation(
                tx, self.hasher, credential, conversation_id
            )
            source = await tx.image_source(actor.session.account_id, conversation_id, image_id)
            if source is None:
                raise ChatImageUnavailableError
            if source.preparation.id != image_id:
                raise RuntimeError("Image read returned another requested source")
            result = owned_value(
                source,
                actor.session.account_id,
                conversation_id,
                access.conversation.pair,
                await tx.now(),
            )
            if not actor.session.is_active(await tx.now()):
                raise UnauthenticatedError
            return result


@dataclass(frozen=True, slots=True)
class ListOwnImagePreparations:
    unit_of_work: ImageReadUnitOfWork
    hasher: SessionHasher

    async def __call__(
        self,
        credential: SessionCredential,
        conversation_id: UUID,
    ) -> tuple[OwnedImagePreparation, ...]:
        async with self.unit_of_work.transaction(conversation_id) as tx:
            actor, access = await authorize_conversation(
                tx, self.hasher, credential, conversation_id
            )
            sources = await tx.image_sources(actor.session.account_id, conversation_id)
            images = tuple(source.preparation for source in sources)
            pending = sum(image.pending for image in images)
            if (
                len(images) > OWNED_IMAGE_LIMIT
                or pending > PENDING_IMAGE_LIMIT
                or len(images) - pending > TERMINAL_IMAGE_LIMIT
                or len({image.id for image in images}) != len(images)
            ):
                raise RuntimeError("Owned image recovery exceeds its actual bounded source set")
            if images != tuple(
                sorted(images, key=lambda image: (image.created_at, image.id.int), reverse=True)
            ):
                raise RuntimeError("Owned image recovery violates newest-source ordering")
            at = await tx.now()
            result = tuple(
                owned_value(
                    source, actor.session.account_id, conversation_id, access.conversation.pair, at
                )
                for source in sources
            )
            if not actor.session.is_active(await tx.now()):
                raise UnauthenticatedError
            return result
