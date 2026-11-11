"""Issue upload transport only between two current, exact owned-source authorizations."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from studymate.application.chat_images.finalize import ChatImageUnavailableError
from studymate.application.chat_images.reads import ImageReadUnitOfWork, owned_value
from studymate.application.identity.sessions import (
    SessionCredential,
    SessionHasher,
    UnauthenticatedError,
)
from studymate.application.media.storage import UploadAccess
from studymate.application.messaging.commands import authorize_conversation
from studymate.application.messaging.ports import MessageContactUnavailableError
from studymate.domain.chat_images import ChatImagePreparation, ChatImageState
from studymate.domain.media import MediaObjectKind, MediaObjectRef


class UploadAccessIssuer(Protocol):
    async def upload_access(
        self, reference: MediaObjectRef, content_type: str, expires_at: datetime
    ) -> UploadAccess: ...


class ChatImageUploadAccessDeniedError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class _UploadSnapshot:
    session_id: UUID
    image: ChatImagePreparation = field(repr=False)


@dataclass(frozen=True, slots=True)
class CreateChatImageUploadAccess:
    unit_of_work: ImageReadUnitOfWork
    hasher: SessionHasher
    storage: UploadAccessIssuer

    async def _snapshot(
        self, credential: SessionCredential, conversation_id: UUID, image_id: UUID
    ) -> _UploadSnapshot:
        async with self.unit_of_work.transaction(conversation_id) as transaction:
            actor, access = await authorize_conversation(
                transaction, self.hasher, credential, conversation_id
            )
            source = await transaction.image_source(
                actor.session.account_id, conversation_id, image_id
            )
            if source is None:
                raise ChatImageUnavailableError
            if source.preparation.id != image_id:
                raise RuntimeError("Upload access differs from the actual requested image source")
            view = owned_value(
                source,
                actor.session.account_id,
                conversation_id,
                access.conversation.pair,
                await transaction.now(),
            )
            if not access.can_send:
                raise MessageContactUnavailableError
            if view.effective_state != ChatImageState.UPLOADING or view.message_outcome is not None:
                raise ChatImageUploadAccessDeniedError
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return _UploadSnapshot(actor.session.id, view.preparation)

    async def __call__(
        self, credential: SessionCredential, conversation_id: UUID, image_id: UUID
    ) -> UploadAccess:
        original = await self._snapshot(credential, conversation_id, image_id)
        access = await self.storage.upload_access(
            MediaObjectRef(image_id, MediaObjectKind.UPLOAD),
            original.image.source.content_type.value,
            original.image.upload_expires_at,
        )
        current = await self._snapshot(credential, conversation_id, image_id)
        if current != original:
            raise ChatImageUploadAccessDeniedError
        return access
