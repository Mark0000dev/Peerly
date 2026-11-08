from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID

import pytest

from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.application.messaging.conversation_list import (
    CONVERSATION_PAGE_SIZE,
    ConversationListCursor,
    ConversationListEntry,
    ConversationListQuery,
    ConversationListTransaction,
    InvalidConversationCursorError,
    ListConversations,
)
from studymate.application.messaging.participants import ChatParticipant, ChatParticipantState
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.identity_store import CREDENTIAL, NOW, IdentityStore
from tests.unit.requests.test_states import request


class Store(IdentityStore):
    def __init__(self) -> None:
        super().__init__()
        self.actor = replace(self.actor, activation_complete=True)
        self.rows: tuple[ConversationListEntry, ...] = ()
        self.queries: tuple[ConversationListQuery, ...] = ()
        self.expire = False

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[ConversationListTransaction]:
        yield self

    async def list_conversations(
        self, query: ConversationListQuery
    ) -> tuple[ConversationListEntry, ...]:
        assert query.actor_id == self.actor.session.account_id
        self.queries += (query,)
        if self.expire:
            self.clock = self.actor.session.expires_at
        return self.rows


class Cursors:
    def __init__(self) -> None:
        self.values: dict[str, tuple[UUID, ConversationListCursor]] = {}

    def encode(self, actor_id: UUID, value: ConversationListCursor) -> str:
        self.values["opaque"] = (actor_id, value)
        return "opaque"

    def decode(self, actor_id: UUID, token: str, now: datetime) -> ConversationListCursor:
        assert now >= NOW
        if token not in self.values or self.values[token][0] != actor_id:
            raise InvalidConversationCursorError
        return self.values[token][1]


def entry(number: int) -> ConversationListEntry:
    return ConversationListEntry(
        UUID(int=number),
        UUID(int=1000 + number),
        NOW - timedelta(hours=1),
        NOW,
        ChatParticipant(UUID(int=3), ChatParticipantState.AVAILABLE),
        request().context,
        None,
        0,
        True,
    )


async def test_empty_conversation_page_does_not_invent_a_thread_or_cursor() -> None:
    store, codec = Store(), Cursors()
    result = await ListConversations(store, Sha256SessionHasher(), codec)(CREDENTIAL)
    assert not result.conversations
    assert result.next_cursor is None
    assert store.queries == (ConversationListQuery(UUID(int=2), NOW, None),)


async def test_twenty_rows_use_one_lookahead_and_an_actor_bound_activity_keyset() -> None:
    store, codec = Store(), Cursors()
    store.rows = tuple(entry(number) for number in range(30, 9, -1))
    usecase = ListConversations(store, Sha256SessionHasher(), codec)
    page = await usecase(CREDENTIAL)
    assert len(page.conversations) == CONVERSATION_PAGE_SIZE
    assert page.next_cursor == "opaque"
    position = codec.values["opaque"][1]
    assert position.conversation_id == UUID(int=11)
    store.rows = (entry(10),)
    store.clock += timedelta(minutes=1)
    last = await usecase(CREDENTIAL, page.next_cursor)
    assert last.conversations == store.rows
    assert last.next_cursor is None
    assert store.queries[-1].as_of == NOW
    assert store.queries[-1].cursor == position


@pytest.mark.parametrize(
    "malformation", ["foreign", "self_peer", "future", "duplicate", "unordered", "overflow"]
)
async def test_private_scope_and_adapter_page_invariants_fail_closed(malformation: str) -> None:
    store = Store()
    row = entry(30)
    if malformation == "foreign":
        context = row.original_context
        assert context.sender_goal is not None
        source = replace(
            context.sender_goal, goal=replace(context.sender_goal.goal, account_id=UUID(int=90))
        )
        row = replace(
            row, original_context=replace(context, sender_id=UUID(int=90), sender_goal=source)
        )
    elif malformation == "self_peer":
        row = replace(row, peer=replace(row.peer, account_id=UUID(int=2)))
    elif malformation == "future":
        row = replace(row, activity_at=NOW + timedelta(seconds=1))
    store.rows = (row,)
    if malformation == "duplicate":
        store.rows += (row,)
    elif malformation == "unordered":
        store.rows += (entry(31),)
    elif malformation == "overflow":
        store.rows = tuple(entry(i) for i in range(40, 18, -1))
    with pytest.raises(RuntimeError):
        await ListConversations(store, Sha256SessionHasher(), Cursors())(CREDENTIAL)


@pytest.mark.parametrize("state", ["unverified", "banned", "unactivated", "deleted", "expired"])
async def test_caller_lifecycle_is_checked_before_private_list_read(state: str) -> None:
    store = Store()
    store.actor = replace(
        store.actor,
        membership=None if state == "unverified" else store.actor.membership,
        banned=state == "banned",
        activation_complete=state != "unactivated",
        deleted_at=NOW if state == "deleted" else None,
    )
    if state == "expired":
        store.clock = store.actor.session.expires_at
    with pytest.raises((UnauthenticatedError, StudentActionDeniedError)):
        await ListConversations(store, Sha256SessionHasher(), Cursors())(CREDENTIAL)
    assert not store.queries


async def test_expired_session_after_query_does_not_return_private_results() -> None:
    store = Store()
    store.expire = True
    store.rows = (entry(30),)
    with pytest.raises(UnauthenticatedError):
        await ListConversations(store, Sha256SessionHasher(), Cursors())(CREDENTIAL)


@pytest.mark.parametrize("token", ["unknown", "x" * 1025])
async def test_bad_cursor_cannot_trigger_a_private_query(token: str) -> None:
    store = Store()
    with pytest.raises(InvalidConversationCursorError):
        await ListConversations(store, Sha256SessionHasher(), Cursors())(CREDENTIAL, token)
    assert not store.queries
