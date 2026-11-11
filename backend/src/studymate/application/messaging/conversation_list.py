"""Bounded accepted threads, actual human activity and caller-private unread state."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from studymate.application.identity.sessions import (
    IdentityReader,
    SessionCredential,
    SessionHasher,
    StudentActionDeniedError,
    UnauthenticatedError,
    require_verified_student,
)
from studymate.application.messaging.participants import ChatParticipant
from studymate.domain.messaging import ConfirmedMessage
from studymate.domain.requests.context import RequestContext
from studymate.domain.time import require_aware

CONVERSATION_PAGE_SIZE = 20
CONVERSATION_CURSOR_LIMIT = 1024


class InvalidConversationCursorError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ConversationListCursor:
    as_of: datetime
    activity_at: datetime
    conversation_id: UUID

    def __post_init__(self) -> None:
        require_aware(self.as_of)
        require_aware(self.activity_at)
        if self.activity_at > self.as_of:
            raise ValueError("Conversation cursor cannot precede its activity source")


class ConversationListCursorCodec(Protocol):
    def encode(self, actor_id: UUID, value: ConversationListCursor) -> str: ...

    def decode(self, actor_id: UUID, token: str, now: datetime) -> ConversationListCursor: ...


@dataclass(frozen=True, slots=True)
class ConversationListEntry:
    conversation_id: UUID
    request_id: UUID
    accepted_at: datetime
    activity_at: datetime
    peer: ChatParticipant = field(repr=False)
    original_context: RequestContext = field(repr=False)
    last_message: ConfirmedMessage | None = field(repr=False)
    unread_count: int
    can_send: bool

    def __post_init__(self) -> None:
        require_aware(self.accepted_at)
        require_aware(self.activity_at)
        if self.activity_at < self.accepted_at:
            raise ValueError("Conversation activity cannot precede actual acceptance")
        if isinstance(self.unread_count, bool) or self.unread_count < 0:
            raise ValueError("Conversation unread count cannot be negative")
        if (
            self.last_message is not None
            and self.last_message.conversation_id != self.conversation_id
        ):
            raise ValueError("Conversation preview must belong to this thread")


@dataclass(frozen=True, slots=True)
class ConversationListQuery:
    actor_id: UUID
    as_of: datetime
    cursor: ConversationListCursor | None


@dataclass(frozen=True, slots=True)
class ConversationListPage:
    conversations: tuple[ConversationListEntry, ...] = field(repr=False)
    next_cursor: str | None


class ConversationListTransaction(IdentityReader, Protocol):
    async def list_conversations(
        self, query: ConversationListQuery
    ) -> tuple[ConversationListEntry, ...]:
        """Participant-filter before private decoding; descending activity/id, at most21."""
        ...


class ConversationListUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[ConversationListTransaction]: ...


@dataclass(frozen=True, slots=True)
class ListConversations:
    unit_of_work: ConversationListUnitOfWork
    hasher: SessionHasher
    cursors: ConversationListCursorCodec

    async def __call__(
        self, credential: SessionCredential, cursor: str | None = None
    ) -> ConversationListPage:
        async with self.unit_of_work.transaction() as transaction:
            actor, now = await require_verified_student(
                transaction, await self.hasher.digest(credential)
            )
            if not actor.activation_complete:
                raise StudentActionDeniedError
            actor_id = actor.session.account_id
            if cursor is not None and len(cursor) > CONVERSATION_CURSOR_LIMIT:
                raise InvalidConversationCursorError
            decoded = self.cursors.decode(actor_id, cursor, now) if cursor is not None else None
            anchor = decoded.as_of if decoded is not None else now
            rows = await transaction.list_conversations(
                ConversationListQuery(actor_id, anchor, decoded)
            )
            if len(rows) > CONVERSATION_PAGE_SIZE + 1:
                raise RuntimeError("Conversation source exceeded its bounded page")
            previous = (
                (decoded.activity_at, decoded.conversation_id) if decoded is not None else None
            )
            for row in rows:
                key = (row.activity_at, row.conversation_id)
                if (
                    actor_id
                    not in (row.original_context.sender_id, row.original_context.recipient_id)
                    or row.peer.account_id == actor_id
                    or row.peer.account_id
                    not in (row.original_context.sender_id, row.original_context.recipient_id)
                    or row.activity_at > anchor
                    or (previous is not None and key >= previous)
                ):
                    raise RuntimeError(
                        "Conversation list lost participant scope or stable page order"
                    )
                previous = key
            page = rows[:CONVERSATION_PAGE_SIZE]
            next_cursor = (
                self.cursors.encode(
                    actor_id,
                    ConversationListCursor(anchor, page[-1].activity_at, page[-1].conversation_id),
                )
                if len(rows) > CONVERSATION_PAGE_SIZE
                else None
            )
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return ConversationListPage(page, next_cursor)
