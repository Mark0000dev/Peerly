import asyncio
import hashlib
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Self
from uuid import UUID, uuid4

import pytest

from studymate.application.chat_images.display import (
    ImageDisplaySource,
    ReadMessageImageDisplay,
    ReadOwnedImageDisplay,
)
from studymate.application.chat_images.finalize import ChatImageUnavailableError
from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.application.media.storage import (
    MediaObjectMissingError,
    MediaStorageUnavailableError,
)
from studymate.domain.media import MAX_PHOTO_BYTES, MediaObjectKind, MediaObjectRef
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.chat_image_store import Store
from tests.unit.identity_store import CREDENTIAL, NOW

DATA = b"synthetic-sanitized-jpeg"


class DisplayStore(Store):
    def __init__(self) -> None:
        super().__init__()
        assert self.access is not None
        self.source: ImageDisplaySource | None = ImageDisplaySource(
            uuid4(),
            3,
            uuid4(),
            self.actor.session.account_id,
            self.access.conversation.id,
            uuid4(),
            None,
            10,
            10,
            len(DATA),
            hashlib.sha256(DATA).digest(),
        )
        self.open_transactions = 0

    @asynccontextmanager
    async def transaction(self, conversation_id: UUID) -> AsyncIterator[Self]:
        assert self.access is None or self.access.conversation.id == conversation_id
        self.open_transactions += 1
        try:
            yield self
        finally:
            self.open_transactions -= 1

    async def owned_display_source(
        self, actor_id: UUID, conversation_id: UUID, image_id: UUID
    ) -> ImageDisplaySource | None:
        del actor_id, conversation_id, image_id
        return self.source

    async def message_display_source(
        self, actor_id: UUID, conversation_id: UUID, message_id: UUID
    ) -> ImageDisplaySource | None:
        del actor_id, conversation_id, message_id
        return self.source


class Reader:
    def __init__(self, store: DisplayStore) -> None:
        self.store = store
        self.callback: Callable[[], Awaitable[None]] | None = None
        self.data = DATA
        self.failure: BaseException | None = None
        self.references: list[MediaObjectRef] = []
        self.stall = False

    async def read(self, reference: MediaObjectRef) -> bytes:
        assert self.store.open_transactions == 0
        assert reference.kind == MediaObjectKind.DISPLAY
        self.references.append(reference)
        if self.callback is not None:
            await self.callback()
        if self.stall:
            await asyncio.Event().wait()
        if self.failure is not None:
            raise self.failure
        return self.data


@pytest.mark.parametrize("owned", [True, False])
async def test_display_rechecks_sql_authority_around_only_display_io(owned: bool) -> None:
    store = DisplayStore()
    assert store.source is not None
    assert store.access is not None
    store.access = replace(store.access, blocked=True, peer_banned=True, peer_deleted=True)
    if not owned:
        store.source = replace(store.source, message_id=uuid4())
    source = store.source
    storage = Reader(store)
    operation = (
        ReadOwnedImageDisplay(store, Sha256SessionHasher(), storage)
        if owned
        else ReadMessageImageDisplay(store, Sha256SessionHasher(), storage)
    )
    resource_id = source.image_id if owned else source.message_id
    assert resource_id is not None
    result = await operation(CREDENTIAL, source.conversation_id, resource_id)
    assert result.data == DATA
    assert result.content_type == "image/jpeg"
    assert storage.references == [source.reference]
    assert "synthetic-sanitized" not in repr(result)
    assert source.sha256.hex() not in repr(source)
    assert store.open_transactions == 0


@pytest.mark.parametrize("fault", ["expired", "session", "banned", "deleted", "source", "missing"])
async def test_authority_or_source_change_during_io_prevents_byte_release(fault: str) -> None:
    store = DisplayStore()
    assert store.source is not None
    initial = store.source
    storage = Reader(store)

    async def change() -> None:
        if fault == "expired":
            store.clock = store.actor.session.expires_at
        elif fault == "session":
            store.actor = replace(store.actor, session=replace(store.actor.session, id=uuid4()))
        elif fault == "banned":
            store.actor = replace(store.actor, banned=True)
        elif fault == "deleted":
            store.actor = replace(store.actor, deleted_at=NOW)
        elif fault == "source":
            store.source = replace(initial, version=initial.version + 1)
        else:
            store.source = None

    storage.callback = change
    error = (
        StudentActionDeniedError
        if fault == "banned"
        else (ChatImageUnavailableError if fault in {"source", "missing"} else UnauthenticatedError)
    )
    with pytest.raises(error):
        await ReadOwnedImageDisplay(store, Sha256SessionHasher(), storage)(
            CREDENTIAL, initial.conversation_id, initial.image_id
        )


@pytest.mark.parametrize(
    "fault", ["empty", "size", "hash", "oversize", "missing", "unavailable", "timeout", "cancel"]
)
async def test_storage_integrity_failures_never_release_bytes(fault: str) -> None:
    store = DisplayStore()
    assert store.source is not None
    source = store.source
    storage = Reader(store)
    if fault == "empty":
        storage.data = b""
    elif fault == "size":
        storage.data = DATA + b"x"
    elif fault == "hash":
        storage.data = b"x" * len(DATA)
    elif fault == "oversize":
        storage.data = b"x" * (MAX_PHOTO_BYTES + 1)
    elif fault == "missing":
        storage.failure = MediaObjectMissingError()
    elif fault == "unavailable":
        storage.failure = MediaStorageUnavailableError()
    elif fault == "timeout":
        storage.failure = TimeoutError()
    else:
        storage.failure = asyncio.CancelledError()
    error = (
        asyncio.CancelledError
        if fault == "cancel"
        else (ChatImageUnavailableError if fault == "missing" else StorageUnavailableError)
    )
    with pytest.raises(error):
        await ReadOwnedImageDisplay(store, Sha256SessionHasher(), storage)(
            CREDENTIAL, source.conversation_id, source.image_id
        )


@pytest.mark.parametrize("fault", ["conversation", "owner", "id", "message"])
async def test_wrong_actual_source_scope_fails_closed(fault: str) -> None:
    store = DisplayStore()
    assert store.source is not None
    source = store.source
    if fault == "conversation":
        store.source = replace(source, conversation_id=uuid4())
    elif fault == "owner":
        store.source = replace(source, account_id=uuid4())
    elif fault == "id":
        store.source = replace(source, image_id=uuid4())
    else:
        store.source = replace(source, message_id=uuid4())
    storage = Reader(store)
    with pytest.raises(RuntimeError, match="authority"):
        await ReadOwnedImageDisplay(store, Sha256SessionHasher(), storage)(
            CREDENTIAL, source.conversation_id, source.image_id
        )
    assert not storage.references


def test_invalid_display_metadata_is_not_a_storage_reference() -> None:
    store = DisplayStore()
    assert store.source is not None
    with pytest.raises(ValueError, match="bounded retained"):
        replace(store.source, sha256=b"bad")
