from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from studymate.application.identity.sessions import (
    SessionCredential,
    SessionHasher,
    UnauthenticatedError,
)
from studymate.application.messaging.commands import authorize_conversation
from studymate.application.messaging.participants import (
    ChatParticipant,
    ChatParticipantSource,
    chat_participant_projection,
)
from studymate.application.messaging.read_positions import (
    ReadPositionTransaction,
    checked_read_position,
)
from studymate.domain.message_reads import ConversationReadPosition
from studymate.domain.messaging import ChatConversation
from studymate.domain.requests.states import ConnectionRequest, RequestState


@dataclass(frozen=True, slots=True)
class ConversationDetails:
    conversation: ChatConversation
    accepted_request: ConnectionRequest = field(repr=False)
    peer: ChatParticipant = field(repr=False)
    read_position: ConversationReadPosition | None
    unread_count: int
    can_send: bool


class ConversationDetailsTransaction(ReadPositionTransaction, Protocol):
    async def accepted_request(
        self, actor_id: UUID, conversation_id: UUID
    ) -> ConnectionRequest | None:
        """Actual accepted FK source only, participant-scoped before private decoding."""
        ...

    async def current_participant(self, account_id: UUID) -> ChatParticipantSource | None: ...

    async def unread_messages(
        self, actor_id: UUID, conversation_id: UUID, through_sequence: int
    ) -> int: ...


class ConversationDetailsUnitOfWork(Protocol):
    def transaction(
        self, conversation_id: UUID
    ) -> AbstractAsyncContextManager[ConversationDetailsTransaction]: ...


@dataclass(frozen=True, slots=True)
class ReadConversationDetails:
    unit_of_work: ConversationDetailsUnitOfWork
    hasher: SessionHasher

    async def __call__(
        self, credential: SessionCredential, conversation_id: UUID
    ) -> ConversationDetails:
        async with self.unit_of_work.transaction(conversation_id) as transaction:
            actor, access = await authorize_conversation(
                transaction, self.hasher, credential, conversation_id
            )
            actor_id, conversation = actor.session.account_id, access.conversation
            request = await transaction.accepted_request(actor_id, conversation_id)
            if (
                request is None
                or request.id != conversation.request_id
                or request.pair != conversation.pair
                or request.conversation_id != conversation.id
                or request.version != conversation.accepted_request_version
                or request.state != RequestState.ACCEPTED
            ):
                raise RuntimeError("Conversation detail lost its actual accepted request source")
            peer_id = (
                conversation.pair.high
                if actor_id == conversation.pair.low
                else conversation.pair.low
            )
            source = await transaction.current_participant(peer_id) if access.can_send else None
            peer = chat_participant_projection(access, actor_id, source)
            position = await transaction.read_position(actor_id, conversation_id)
            if position is not None:
                checked_read_position(position, access, actor_id)
                if position.through_sequence >= conversation.next_message_sequence:
                    raise RuntimeError("Read marker exceeds its actual confirmed message source")
            unread = await transaction.unread_messages(
                actor_id, conversation_id, position.through_sequence if position is not None else 0
            )
            if isinstance(unread, bool) or not 0 <= unread < conversation.next_message_sequence:
                raise RuntimeError(
                    "Conversation unread projection exceeds its actual message range"
                )
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return ConversationDetails(
                conversation, request, peer, position, unread, access.can_send
            )
