import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import replace
from uuid import UUID, uuid4

import pytest

from studymate.application.discovery.photos import DiscoveryPhotoTransaction, ReadDiscoveryPhoto
from studymate.application.discovery.profiles import (
    DiscoveryProfileSource,
    DiscoveryProfileUnavailableError,
)
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.domain.media import MediaObjectKind, MediaObjectRef
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.identity_store import CREDENTIAL, NOW, IdentityStore
from tests.unit.test_discovery_profiles import TARGET, source


class Store(IdentityStore):
    def __init__(self) -> None:
        super().__init__()
        self.actor = replace(self.actor, activation_complete=True)
        self.sources = {
            account_id: source(account_id, self)
            for account_id in (self.actor.session.account_id, TARGET)
        }
        photo = self.sources[TARGET].setup.photo
        assert photo is not None
        self.reference: MediaObjectRef | None = MediaObjectRef(
            photo.upload_id, MediaObjectKind.DISPLAY, uuid4()
        )
        self.blocked = False
        self.active = 0

    @asynccontextmanager
    async def transaction(self, target_id: UUID) -> AsyncIterator[DiscoveryPhotoTransaction]:
        assert target_id == TARGET
        self.active += 1
        try:
            yield self
        finally:
            self.active -= 1

    async def profile_source(self, account_id: UUID) -> DiscoveryProfileSource | None:
        return self.sources.get(account_id)

    async def pair_blocked(self, actor_id: UUID, target_id: UUID) -> bool:
        assert actor_id == self.actor.session.account_id
        assert target_id == TARGET
        return self.blocked

    async def display_reference(
        self, account_id: UUID, photo_version: int
    ) -> MediaObjectRef | None:
        assert account_id == TARGET
        assert photo_version > 0
        return self.reference


class Storage:
    def __init__(self, store: Store, during_read: Callable[[], None]) -> None:
        self.store = store
        self.during_read = during_read
        self.reads: list[MediaObjectRef] = []

    async def read(self, reference: MediaObjectRef) -> bytes:
        assert self.store.active == 0
        self.reads.append(reference)
        self.during_read()
        await asyncio.sleep(0)
        return b"controlled display bytes"


async def test_peer_photo_reads_only_display_with_no_sql_held_during_storage() -> None:
    store = Store()
    storage = Storage(store, lambda: None)
    result = await ReadDiscoveryPhoto(store, Sha256SessionHasher(), storage)(CREDENTIAL, TARGET, 1)
    assert result == b"controlled display bytes"
    assert storage.reads == [store.reference]
    assert store.active == 0


@pytest.mark.parametrize("change", ["blocked", "hidden", "photo", "attempt", "deleted", "expired"])
async def test_peer_photo_reauthorizes_after_storage_wait(change: str) -> None:
    store = Store()

    def during_read() -> None:
        if change == "blocked":
            store.blocked = True
        elif change == "hidden":
            target = store.sources[TARGET]
            assert target.setup.lifecycle is not None
            store.sources[TARGET] = replace(
                target,
                setup=replace(
                    target.setup,
                    lifecycle=target.setup.lifecycle.with_visibility(hidden=True, at=NOW),
                ),
            )
        elif change == "photo":
            target = store.sources[TARGET]
            assert target.setup.photo is not None
            store.sources[TARGET] = replace(
                target,
                setup=replace(
                    target.setup, photo=replace(target.setup.photo, version=2, upload_id=uuid4())
                ),
            )
        elif change == "attempt":
            assert store.reference is not None
            store.reference = replace(store.reference, attempt_id=uuid4())
        elif change == "deleted":
            store.actor = replace(store.actor, deleted_at=NOW)
        else:
            store.clock = store.actor.session.expires_at

    storage = Storage(store, during_read)
    error = (
        UnauthenticatedError
        if change in {"deleted", "expired"}
        else DiscoveryProfileUnavailableError
    )
    with pytest.raises(error):
        await ReadDiscoveryPhoto(store, Sha256SessionHasher(), storage)(CREDENTIAL, TARGET, 1)
    assert store.active == 0
    assert len(storage.reads) == 1


@pytest.mark.parametrize("version", [0, -1, True])
async def test_peer_photo_requires_positive_revision(version: int) -> None:
    store = Store()
    storage = Storage(store, lambda: None)
    with pytest.raises(ValueError, match="positive"):
        await ReadDiscoveryPhoto(store, Sha256SessionHasher(), storage)(CREDENTIAL, TARGET, version)
    assert not storage.reads


async def test_peer_photo_never_reads_a_foreign_storage_reference() -> None:
    store = Store()
    store.reference = MediaObjectRef(uuid4(), MediaObjectKind.DISPLAY, uuid4())
    storage = Storage(store, lambda: None)
    with pytest.raises(RuntimeError, match="disagrees"):
        await ReadDiscoveryPhoto(store, Sha256SessionHasher(), storage)(CREDENTIAL, TARGET, 1)
    assert not storage.reads


async def test_cancelled_peer_photo_does_not_keep_permission_locks() -> None:
    store = Store()

    def cancel() -> None:
        raise asyncio.CancelledError

    storage = Storage(store, cancel)
    with pytest.raises(asyncio.CancelledError):
        await ReadDiscoveryPhoto(store, Sha256SessionHasher(), storage)(CREDENTIAL, TARGET, 1)
    assert store.active == 0
