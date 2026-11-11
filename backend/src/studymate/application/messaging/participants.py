"""Accepted membership grants minimal current chat identity, independently of Discovery."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from studymate.application.identity.sessions import (
    SessionCredential,
    SessionHasher,
    UnauthenticatedError,
)
from studymate.application.media.storage import MediaReader
from studymate.application.messaging.commands import authorize_conversation
from studymate.application.messaging.ports import (
    ConversationAccess,
    ConversationUnavailableError,
    MessageTransaction,
)
from studymate.domain.media import MediaObjectKind, MediaObjectRef
from studymate.domain.profiles import DisplayName


class ChatParticipantState(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DELETED = "deleted"


@dataclass(frozen=True, slots=True)
class ChatParticipantSource:
    account_id: UUID
    name: DisplayName | None = field(repr=False)
    photo_version: int | None
    photo_reference: MediaObjectRef | None = field(repr=False)

    def __post_init__(self) -> None:
        if (self.photo_version is None) != (self.photo_reference is None):
            raise ValueError("Chat avatar version and display source must agree")
        if (
            self.photo_reference is not None
            and self.photo_reference.kind != MediaObjectKind.DISPLAY
        ):
            raise ValueError("Chat identity cannot grant an original media object")
        if self.photo_version is not None and (
            isinstance(self.photo_version, bool) or self.photo_version < 1
        ):
            raise ValueError("Chat avatar requires a positive current version")


@dataclass(frozen=True, slots=True)
class ChatParticipant:
    account_id: UUID
    state: ChatParticipantState
    name: DisplayName | None = field(default=None, repr=False)
    photo_version: int | None = None


def chat_participant_projection(
    access: ConversationAccess, actor_id: UUID, source: ChatParticipantSource | None
) -> ChatParticipant:
    pair = access.conversation.pair
    if actor_id not in (pair.low, pair.high):
        raise RuntimeError("Chat identity projection lacks its accepted actor")
    peer_id = pair.high if actor_id == pair.low else pair.low
    if access.peer_deleted:
        return ChatParticipant(peer_id, ChatParticipantState.DELETED)
    if not access.can_send:
        return ChatParticipant(peer_id, ChatParticipantState.UNAVAILABLE)
    if source is None or source.account_id != peer_id:
        raise RuntimeError("Accepted chat lost its current participant identity source")
    return ChatParticipant(
        peer_id, ChatParticipantState.AVAILABLE, source.name, source.photo_version
    )


class ChatParticipantTransaction(MessageTransaction, Protocol):
    async def current_participant(self, account_id: UUID) -> ChatParticipantSource | None:
        """Minimal source facts only. Accepted membership is checked by the use case."""
        ...


class ChatParticipantUnitOfWork(Protocol):
    def transaction(
        self, conversation_id: UUID
    ) -> AbstractAsyncContextManager[ChatParticipantTransaction]: ...


@dataclass(frozen=True, slots=True)
class ReadChatParticipant:
    unit_of_work: ChatParticipantUnitOfWork
    hasher: SessionHasher

    async def __call__(
        self, credential: SessionCredential, conversation_id: UUID
    ) -> ChatParticipant:
        async with self.unit_of_work.transaction(conversation_id) as transaction:
            actor, access = await authorize_conversation(
                transaction, self.hasher, credential, conversation_id
            )
            pair = access.conversation.pair
            peer_id = pair.high if actor.session.account_id == pair.low else pair.low
            source = await transaction.current_participant(peer_id) if access.can_send else None
            result = chat_participant_projection(access, actor.session.account_id, source)
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return result


@dataclass(frozen=True, slots=True)
class ReadChatAvatar:
    unit_of_work: ChatParticipantUnitOfWork
    hasher: SessionHasher
    storage: MediaReader

    async def _reference(
        self, credential: SessionCredential, conversation_id: UUID, photo_version: int
    ) -> MediaObjectRef:
        async with self.unit_of_work.transaction(conversation_id) as transaction:
            actor, access = await authorize_conversation(
                transaction, self.hasher, credential, conversation_id
            )
            if not access.can_send:
                raise ConversationUnavailableError
            pair = access.conversation.pair
            peer_id = pair.high if actor.session.account_id == pair.low else pair.low
            source = await transaction.current_participant(peer_id)
            if (
                source is None
                or source.photo_version != photo_version
                or source.photo_reference is None
            ):
                raise ConversationUnavailableError
            if source.account_id != peer_id:
                raise RuntimeError("Chat avatar source belongs to another participant")
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return source.photo_reference

    async def __call__(
        self, credential: SessionCredential, conversation_id: UUID, photo_version: int
    ) -> bytes:
        if isinstance(photo_version, bool) or photo_version < 1:
            raise ValueError("Chat avatar version must be positive")
        reference = await self._reference(credential, conversation_id, photo_version)
        data = await self.storage.read(reference)
        if await self._reference(credential, conversation_id, photo_version) != reference:
            raise ConversationUnavailableError
        return data
