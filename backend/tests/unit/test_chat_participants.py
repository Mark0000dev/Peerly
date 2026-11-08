from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from uuid import UUID, uuid4

import pytest

from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.messaging.participants import (
    ChatParticipantSource,
    ChatParticipantState,
    ChatParticipantTransaction,
    ReadChatAvatar,
    ReadChatParticipant,
)
from studymate.application.messaging.ports import ConversationUnavailableError
from studymate.domain.media import MediaObjectKind, MediaObjectRef
from studymate.domain.profiles import DisplayName
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.identity_store import CREDENTIAL
from tests.unit.test_message_commands import Store as MessageStore


class Store(MessageStore):
    def __init__(self) -> None:
        super().__init__()
        assert self.access is not None
        self.source: ChatParticipantSource | None = ChatParticipantSource(
            UUID(int=3),
            DisplayName("Synthetic peer"),
            1,
            MediaObjectRef(uuid4(), MediaObjectKind.DISPLAY, uuid4()),
        )
        self.in_transaction = False
        self.expire_on_source = False

    @asynccontextmanager
    async def transaction(self, conversation_id: UUID) -> AsyncIterator[ChatParticipantTransaction]:
        async with super().transaction(conversation_id):
            self.in_transaction = True
            try:
                yield self
            finally:
                self.in_transaction = False

    async def current_participant(self, account_id: UUID) -> ChatParticipantSource | None:
        assert account_id == UUID(int=3)
        if self.expire_on_source:
            self.clock = self.actor.session.expires_at
        return self.source

    def conversation_id(self) -> UUID:
        assert self.access is not None
        return self.access.conversation.id


class Storage:
    def __init__(self, store: Store, change: str = "none") -> None:
        self.store = store
        self.change = change
        self.reads = 0

    async def read(self, reference: MediaObjectRef) -> bytes:
        assert not self.store.in_transaction
        assert reference.kind == MediaObjectKind.DISPLAY
        self.reads += 1
        assert self.store.access is not None
        if self.change == "delete":
            self.store.access = replace(self.store.access, peer_deleted=True)
        elif self.change == "block":
            self.store.access = replace(self.store.access, blocked=True)
        elif self.change == "replace":
            assert self.store.source is not None
            self.store.source = replace(
                self.store.source,
                photo_reference=MediaObjectRef(uuid4(), MediaObjectKind.DISPLAY, uuid4()),
            )
        elif self.change == "expire":
            self.store.clock = self.store.actor.session.expires_at
        return b"synthetic-sanitized-display"


async def test_minimal_current_identity_is_accepted_member_scoped_not_discovery_scoped() -> None:
    store = Store()
    result = await ReadChatParticipant(store, Sha256SessionHasher())(
        CREDENTIAL, store.conversation_id()
    )
    assert result.state == ChatParticipantState.AVAILABLE
    assert result.name == DisplayName("Synthetic peer")
    assert result.photo_version == 1
    assert "Synthetic peer" not in repr(result)


@pytest.mark.parametrize("state", ["deleted", "blocked", "banned", "unverified"])
async def test_unavailable_peer_is_neutral_and_deleted_identity_is_always_masked(
    state: str,
) -> None:
    store = Store()
    assert store.access is not None
    store.access = replace(
        store.access,
        peer_deleted=state == "deleted",
        blocked=state == "blocked",
        peer_banned=state == "banned",
        peer_verified=state != "unverified",
    )
    result = await ReadChatParticipant(store, Sha256SessionHasher())(
        CREDENTIAL, store.conversation_id()
    )
    assert result.state == (
        ChatParticipantState.DELETED if state == "deleted" else ChatParticipantState.UNAVAILABLE
    )
    assert result.name is None
    assert result.photo_version is None
    storage = Storage(store)
    with pytest.raises(ConversationUnavailableError):
        await ReadChatAvatar(store, Sha256SessionHasher(), storage)(
            CREDENTIAL, store.conversation_id(), 1
        )
    assert storage.reads == 0


async def test_chat_avatar_reads_only_current_display_outside_sql_transaction() -> None:
    store = Store()
    storage = Storage(store)
    assert (
        await ReadChatAvatar(store, Sha256SessionHasher(), storage)(
            CREDENTIAL, store.conversation_id(), 1
        )
        == b"synthetic-sanitized-display"
    )
    assert storage.reads == 1
    assert not store.in_transaction


@pytest.mark.parametrize("change", ["delete", "block", "replace", "expire"])
async def test_chat_avatar_rechecks_current_reference_and_authority_after_storage_wait(
    change: str,
) -> None:
    store = Store()
    storage = Storage(store, change)
    expected = UnauthenticatedError if change == "expire" else ConversationUnavailableError
    with pytest.raises(expected):
        await ReadChatAvatar(store, Sha256SessionHasher(), storage)(
            CREDENTIAL, store.conversation_id(), 1
        )
    assert storage.reads == 1


async def test_chat_current_identity_rejects_wrong_peer_adapter_source() -> None:
    store = Store()
    assert store.source is not None
    store.source = replace(store.source, account_id=uuid4())
    with pytest.raises(RuntimeError, match="participant identity source"):
        await ReadChatParticipant(store, Sha256SessionHasher())(CREDENTIAL, store.conversation_id())


async def test_chat_avatar_does_not_grant_an_old_current_version() -> None:
    store = Store()
    storage = Storage(store)
    with pytest.raises(ConversationUnavailableError):
        await ReadChatAvatar(store, Sha256SessionHasher(), storage)(
            CREDENTIAL, store.conversation_id(), 2
        )
    assert storage.reads == 0


@pytest.mark.parametrize(
    "shape",
    ["version_without_reference", "reference_without_version", "zero", "boolean", "original"],
)
def test_chat_source_rejects_inconsistent_versions_and_original_media(shape: str) -> None:
    reference = MediaObjectRef(
        uuid4(),
        MediaObjectKind.ORIGINAL if shape == "original" else MediaObjectKind.DISPLAY,
        uuid4(),
    )
    version = (
        None
        if shape == "reference_without_version"
        else 0
        if shape == "zero"
        else True
        if shape == "boolean"
        else 1
    )
    with pytest.raises(ValueError, match=r"agree|original|positive"):
        ChatParticipantSource(
            UUID(int=3),
            DisplayName("Synthetic peer"),
            version,
            None if shape == "version_without_reference" else reference,
        )


@pytest.mark.parametrize("version", [0, True, -1])
async def test_avatar_invalid_version_never_reads_storage(version: int) -> None:
    store = Store()
    storage = Storage(store)
    with pytest.raises(ValueError, match="positive"):
        await ReadChatAvatar(store, Sha256SessionHasher(), storage)(
            CREDENTIAL, store.conversation_id(), version
        )
    assert storage.reads == 0


async def test_avatar_adapter_cannot_substitute_another_peer_source() -> None:
    store = Store()
    assert store.source is not None
    store.source = replace(store.source, account_id=uuid4())
    storage = Storage(store)
    with pytest.raises(RuntimeError, match="another participant"):
        await ReadChatAvatar(store, Sha256SessionHasher(), storage)(
            CREDENTIAL, store.conversation_id(), 1
        )
    assert storage.reads == 0


async def test_absent_participant_is_an_adapter_source_failure_not_fabricated_identity() -> None:
    store = Store()
    store.source = None
    with pytest.raises(RuntimeError, match="identity source"):
        await ReadChatParticipant(store, Sha256SessionHasher())(CREDENTIAL, store.conversation_id())


@pytest.mark.parametrize("resource", ["identity", "avatar"])
async def test_final_session_check_covers_current_participant_projection(resource: str) -> None:
    store = Store()
    store.expire_on_source = True
    storage = Storage(store)
    result = (
        ReadChatParticipant(store, Sha256SessionHasher())(CREDENTIAL, store.conversation_id())
        if resource == "identity"
        else ReadChatAvatar(store, Sha256SessionHasher(), storage)(
            CREDENTIAL, store.conversation_id(), 1
        )
    )
    with pytest.raises(UnauthenticatedError):
        await result
    assert storage.reads == 0
