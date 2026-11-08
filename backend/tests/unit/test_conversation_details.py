from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from uuid import UUID, uuid4

import pytest

from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.messaging.conversation_details import (
    ConversationDetailsTransaction,
    ReadConversationDetails,
)
from studymate.application.messaging.participants import ChatParticipantSource, ChatParticipantState
from studymate.domain.message_reads import ConversationReadPosition
from studymate.domain.profiles import DisplayName
from studymate.domain.requests.states import ConnectionRequest
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.requests.test_states import request
from tests.unit.test_message_reads import HASHER
from tests.unit.test_message_reads import Store as ReadStore


class Store(ReadStore):
    def __init__(self) -> None:
        super().__init__()
        assert self.access is not None
        self.accepted: ConnectionRequest | None = request().accept(
            UUID(int=3), self.access.conversation.id, NOW
        )
        self.access = replace(
            self.access,
            conversation=replace(
                self.access.conversation,
                request_id=self.accepted.id,
                relationship_id=self.accepted.relationship_id,
            ),
        )
        self.unread = 0
        self.expire_details = False

    @asynccontextmanager
    async def transaction(
        self, conversation_id: UUID
    ) -> AsyncIterator[ConversationDetailsTransaction]:
        async with super().transaction(conversation_id):
            yield self

    async def accepted_request(
        self, actor_id: UUID, conversation_id: UUID
    ) -> ConnectionRequest | None:
        assert actor_id == self.actor.session.account_id
        assert self.access is not None
        assert conversation_id == self.access.conversation.id
        return self.accepted

    async def current_participant(self, account_id: UUID) -> ChatParticipantSource:
        assert account_id == UUID(int=3)
        return ChatParticipantSource(account_id, DisplayName("Synthetic peer"), None, None)

    async def unread_messages(
        self, actor_id: UUID, conversation_id: UUID, through_sequence: int
    ) -> int:
        assert actor_id == self.actor.session.account_id
        assert self.access is not None
        assert conversation_id == self.access.conversation.id
        assert through_sequence == 0
        if self.expire_details:
            self.clock = self.actor.session.expires_at
        return self.unread

    def conversation_id(self) -> UUID:
        assert self.access is not None
        return self.access.conversation.id


async def test_new_conversation_has_actual_request_context_without_fake_message_or_read_ack() -> (
    None
):
    store = Store()
    details = await ReadConversationDetails(store, HASHER)(CREDENTIAL, store.conversation_id())
    assert details.accepted_request == store.accepted
    assert details.accepted_request.message.text == "Explicit reviewed text"
    assert details.peer.name == DisplayName("Synthetic peer")
    assert details.can_send
    assert details.read_position is None
    assert details.unread_count == 0
    assert details.conversation.next_message_sequence == 1
    assert not store.operations
    assert not store.saved_positions
    assert "Explicit reviewed text" not in repr(details)


@pytest.mark.parametrize("state", ["blocked", "deleted", "banned", "unverified"])
async def test_unavailable_peer_preserves_exact_accepted_context_but_no_new_identity_or_send(
    state: str,
) -> None:
    store = Store()
    assert store.access is not None
    store.access = replace(
        store.access,
        blocked=state == "blocked",
        peer_deleted=state == "deleted",
        peer_banned=state == "banned",
        peer_verified=state != "unverified",
    )
    details = await ReadConversationDetails(store, HASHER)(CREDENTIAL, store.conversation_id())
    assert details.accepted_request == store.accepted
    assert not details.can_send
    assert details.peer.name is None
    assert details.peer.photo_version is None
    assert details.peer.state == (
        ChatParticipantState.DELETED if state == "deleted" else ChatParticipantState.UNAVAILABLE
    )


@pytest.mark.parametrize("malformation", ["absent", "other_request", "other_conversation"])
async def test_detail_requires_actual_accepted_request_source_and_not_arbitrary_snapshot(
    malformation: str,
) -> None:
    store = Store()
    assert store.accepted is not None
    store.accepted = (
        None
        if malformation == "absent"
        else replace(store.accepted, id=uuid4())
        if malformation == "other_request"
        else replace(store.accepted, conversation_id=uuid4())
    )
    with pytest.raises(RuntimeError, match="actual accepted request source"):
        await ReadConversationDetails(store, HASHER)(CREDENTIAL, store.conversation_id())


@pytest.mark.parametrize("unread", [-1, True, 1])
async def test_unread_projection_cannot_exceed_actual_message_range(unread: int) -> None:
    store = Store()
    store.unread = unread
    with pytest.raises(RuntimeError, match="actual message range"):
        await ReadConversationDetails(store, HASHER)(CREDENTIAL, store.conversation_id())


async def test_current_private_position_cannot_reference_a_future_message() -> None:
    store = Store()
    assert store.access is not None
    store.position = ConversationReadPosition(
        uuid4(),
        store.conversation_id(),
        store.access.conversation.pair,
        store.actor.session.account_id,
        1,
        1,
        NOW,
    )
    with pytest.raises(RuntimeError, match="actual confirmed message source"):
        await ReadConversationDetails(store, HASHER)(CREDENTIAL, store.conversation_id())


async def test_session_is_checked_after_private_context_and_unread_queries() -> None:
    store = Store()
    store.expire_details = True
    with pytest.raises(UnauthenticatedError):
        await ReadConversationDetails(store, HASHER)(CREDENTIAL, store.conversation_id())
