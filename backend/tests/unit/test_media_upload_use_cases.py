from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID

import pytest

from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.media.uploads import (
    ChangePhotoUpload,
    MediaIntent,
    MediaTransaction,
    PhotoUploadCommand,
    ReadOwnPhotoUpload,
    StartPhotoCommand,
    StartPhotoUpload,
    UploadAction,
    UploadBudget,
)
from studymate.domain.media import (
    PhotoContentType,
    PhotoRevision,
    PhotoSource,
    PhotoUpload,
    PhotoUploadState,
)
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.identity_store import CREDENTIAL, NOW, IdentityStore


class Store(IdentityStore):
    def __init__(self, *, expire_before_commit: bool = False) -> None:
        super().__init__()
        self.versions: dict[tuple[UUID, int], PhotoUpload] = {}
        self.current: dict[UUID, PhotoUpload] = {}
        self.intents: dict[str, MediaIntent] = {}
        self.expire_before_commit = expire_before_commit

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[MediaTransaction]:
        versions, current, intents = self.versions.copy(), self.current.copy(), self.intents.copy()
        try:
            yield self
        except BaseException:
            self.versions, self.current, self.intents = versions, current, intents
            raise

    async def current_photo(self, account_id: UUID) -> PhotoRevision | None:
        assert account_id == self.actor.session.account_id
        return None

    async def upload(
        self, account_id: UUID, upload_id: UUID, version: int | None = None
    ) -> PhotoUpload | None:
        assert account_id == self.actor.session.account_id
        return (
            self.current.get(upload_id)
            if version is None
            else self.versions.get((upload_id, version))
        )

    async def expire_pending_uploads(self, account_id: UUID, at: datetime) -> None:
        assert account_id == self.actor.session.account_id
        for value in tuple(self.current.values()):
            expired = value.expire(at)
            if expired is not value:
                await self.save_upload(expired)

    async def upload_budget(self, account_id: UUID, since: datetime) -> UploadBudget:
        assert account_id == self.actor.session.account_id
        starts = tuple(
            value.created_at for value in self.current.values() if value.created_at > since
        )
        pending = tuple(value for value in self.current.values() if value.pending)
        return UploadBudget(
            len(starts),
            min(starts, default=None),
            len(pending),
            min((value.upload_expires_at for value in pending), default=None),
        )

    async def media_intent(self, account_id: UUID, key: IntentKey) -> MediaIntent | None:
        assert account_id == self.actor.session.account_id
        return self.intents.get(key.value)

    async def create_upload(self, value: PhotoUpload) -> None:
        await self.save_upload(value)

    async def save_upload(self, value: PhotoUpload) -> None:
        self.versions[value.id, value.version] = value
        self.current[value.id] = value

    async def remember_media_intent(
        self, account_id: UUID, key: IntentKey, intent: MediaIntent, at: datetime
    ) -> None:
        assert account_id == self.actor.session.account_id
        assert at == self.clock
        self.intents[key.value] = intent
        if self.expire_before_commit:
            self.clock = self.actor.session.expires_at


def command() -> StartPhotoCommand:
    return StartPhotoCommand(
        CREDENTIAL,
        PhotoSource(10, bytes(range(32)), PhotoContentType.PNG),
        0,
        IntentKey("synthetic-start"),
    )


def start_service(store: Store) -> StartPhotoUpload:
    return StartPhotoUpload(store, Sha256SessionHasher(), HmacIntentFingerprinter(bytes(range(32))))


async def test_upload_expiry_before_commit_rolls_back_both_intent_and_history() -> None:
    store = Store(expire_before_commit=True)
    with pytest.raises(UnauthenticatedError):
        await start_service(store)(command())
    assert store.versions == {}
    assert store.current == {}
    assert store.intents == {}


async def test_finalization_expiry_before_commit_rolls_back_queued_state() -> None:
    store = Store()
    original = await start_service(store)(command())
    store.expire_before_commit = True
    change = ChangePhotoUpload(
        store, Sha256SessionHasher(), HmacIntentFingerprinter(bytes(range(32)))
    )
    with pytest.raises(UnauthenticatedError):
        await change(
            PhotoUploadCommand(
                CREDENTIAL, original.id, UploadAction.FINALIZE, IntentKey("synthetic-finalize")
            )
        )
    assert store.current[original.id] == original
    assert len(store.versions) == 1
    assert set(store.intents) == {command().intent_key.value}


async def test_missing_replay_snapshot_is_not_a_fabricated_success() -> None:
    store = Store()
    start = start_service(store)
    await start(command())
    store.versions.clear()
    with pytest.raises(RuntimeError, match="result is unavailable"):
        await start(command())


async def test_status_expiration_appends_real_history() -> None:
    store = Store()
    original = await start_service(store)(command())
    store.clock = NOW + timedelta(minutes=15)
    result = await ReadOwnPhotoUpload(store, Sha256SessionHasher())(CREDENTIAL, original.id)
    assert result.state == PhotoUploadState.EXPIRED
    assert store.versions[original.id, original.version] == original
    assert store.current[original.id] == result


@pytest.mark.parametrize("version", [-1, True])
def test_expected_photo_revision_is_nonnegative_integer(version: int) -> None:
    with pytest.raises(ValueError, match="nonnegative"):
        replace(command(), expected_photo_version=version)
