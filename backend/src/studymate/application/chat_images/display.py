"""Private sanitized display reads with SQL authority rechecked after object I/O."""

import asyncio
import hashlib
import hmac
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Literal, Protocol
from uuid import UUID

from studymate.application.chat_images.finalize import ChatImageUnavailableError
from studymate.application.chat_images.reads import ReadyImageInfo
from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import (
    IdentitySnapshot,
    SessionCredential,
    SessionHasher,
    UnauthenticatedError,
)
from studymate.application.media.processing import InvalidImageError
from studymate.application.media.storage import (
    MediaObjectMissingError,
    MediaReader,
    MediaStorageUnavailableError,
)
from studymate.application.messaging.commands import authorize_conversation
from studymate.application.messaging.ports import ConversationAuthority
from studymate.domain.media import MAX_PHOTO_BYTES, SHA256_LENGTH, MediaObjectKind, MediaObjectRef

DISPLAY_READ_SECONDS = 20


@dataclass(frozen=True, slots=True)
class ImageDisplaySource:
    image_id: UUID
    version: int
    attempt_id: UUID
    account_id: UUID
    conversation_id: UUID
    client_message_id: UUID
    message_id: UUID | None
    width: int
    height: int
    size: int
    sha256: bytes = field(repr=False)

    def __post_init__(self) -> None:
        ReadyImageInfo(self.attempt_id, self.width, self.height, self.size)
        if self.version < 1 or self.size > MAX_PHOTO_BYTES or len(self.sha256) != SHA256_LENGTH:
            raise ValueError("Image display requires its actual bounded retained rendition")

    @property
    def reference(self) -> MediaObjectRef:
        return MediaObjectRef(self.image_id, MediaObjectKind.DISPLAY, self.attempt_id)


@dataclass(frozen=True, slots=True)
class ImageDisplayBytes:
    data: bytes = field(repr=False)
    width: int
    height: int
    content_type: Literal["image/jpeg"] = "image/jpeg"


class ImageDisplayTransaction(ConversationAuthority, Protocol):
    async def owned_display_source(
        self,
        actor_id: UUID,
        conversation_id: UUID,
        image_id: UUID,
    ) -> ImageDisplaySource | None: ...

    async def message_display_source(
        self,
        actor_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
    ) -> ImageDisplaySource | None: ...


class ImageDisplayUnitOfWork(Protocol):
    def transaction(
        self,
        conversation_id: UUID,
    ) -> AbstractAsyncContextManager[ImageDisplayTransaction]: ...


@dataclass(frozen=True, slots=True)
class DisplayRequest:
    credential: SessionCredential = field(repr=False)
    conversation_id: UUID
    resource_id: UUID
    owned: bool


async def authorized_source(
    transaction: ImageDisplayTransaction,
    hasher: SessionHasher,
    request: DisplayRequest,
) -> tuple[IdentitySnapshot, ImageDisplaySource]:
    credential, conversation_id, resource_id, owned = (
        request.credential,
        request.conversation_id,
        request.resource_id,
        request.owned,
    )
    actor, access = await authorize_conversation(transaction, hasher, credential, conversation_id)
    actor_id = actor.session.account_id
    source = (
        await transaction.owned_display_source(actor_id, conversation_id, resource_id)
        if owned
        else await transaction.message_display_source(actor_id, conversation_id, resource_id)
    )
    if source is None:
        raise ChatImageUnavailableError
    if (
        source.conversation_id != conversation_id
        or source.account_id not in (access.conversation.pair.low, access.conversation.pair.high)
        or (
            owned
            and (
                source.account_id != actor_id
                or source.image_id != resource_id
                or source.message_id is not None
            )
        )
        or (not owned and source.message_id != resource_id)
    ):
        raise RuntimeError("Image display source differs from actual owner/message authority")
    if not actor.session.is_active(await transaction.now()):
        raise UnauthenticatedError
    return actor, source


async def read_display(
    uow: ImageDisplayUnitOfWork,
    hasher: SessionHasher,
    storage: MediaReader,
    request: DisplayRequest,
) -> ImageDisplayBytes:
    async with uow.transaction(request.conversation_id) as transaction:
        initial, source = await authorized_source(transaction, hasher, request)
    # Both the transaction and its session have ended before private object I/O.
    try:
        async with asyncio.timeout(DISPLAY_READ_SECONDS):
            data = await storage.read(source.reference)
    except MediaObjectMissingError:
        raise ChatImageUnavailableError from None
    except (MediaStorageUnavailableError, InvalidImageError, TimeoutError) as error:
        raise StorageUnavailableError from error
    if (
        not data
        or len(data) > MAX_PHOTO_BYTES
        or len(data) != source.size
        or not hmac.compare_digest(hashlib.sha256(data).digest(), source.sha256)
    ):
        raise StorageUnavailableError
    async with uow.transaction(request.conversation_id) as transaction:
        final, current = await authorized_source(transaction, hasher, request)
        if (initial.session.id, initial.session.account_id) != (
            final.session.id,
            final.session.account_id,
        ):
            raise UnauthenticatedError
        if current != source:
            raise ChatImageUnavailableError
    return ImageDisplayBytes(data, source.width, source.height)


@dataclass(frozen=True, slots=True)
class ReadOwnedImageDisplay:
    unit_of_work: ImageDisplayUnitOfWork
    hasher: SessionHasher
    storage: MediaReader

    async def __call__(
        self, credential: SessionCredential, conversation_id: UUID, image_id: UUID
    ) -> ImageDisplayBytes:
        return await read_display(
            self.unit_of_work,
            self.hasher,
            self.storage,
            DisplayRequest(credential, conversation_id, image_id, True),
        )


@dataclass(frozen=True, slots=True)
class ReadMessageImageDisplay:
    unit_of_work: ImageDisplayUnitOfWork
    hasher: SessionHasher
    storage: MediaReader

    async def __call__(
        self, credential: SessionCredential, conversation_id: UUID, message_id: UUID
    ) -> ImageDisplayBytes:
        return await read_display(
            self.unit_of_work,
            self.hasher,
            self.storage,
            DisplayRequest(credential, conversation_id, message_id, False),
        )
