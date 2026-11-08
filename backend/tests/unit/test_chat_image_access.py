from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Self
from uuid import UUID, uuid4

import pytest

from studymate.application.chat_images.access import (
    ChatImageUploadAccessDeniedError,
    CreateChatImageUploadAccess,
)
from studymate.application.chat_images.finalize import ChatImageUnavailableError
from studymate.application.chat_images.reads import ImagePreparationSource
from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.application.media.storage import MediaStorageUnavailableError, UploadAccess
from studymate.application.messaging.ports import MessageContactUnavailableError
from studymate.domain.media import MediaObjectKind, MediaObjectRef
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.chat_images.test_reads import ReadStore, image
from tests.unit.identity_store import CREDENTIAL, NOW


class AccessStore(ReadStore):
    def __init__(self) -> None:
        super().__init__()
        self.in_transaction = False

    @asynccontextmanager
    async def transaction(self, conversation_id: UUID) -> AsyncIterator[Self]:
        async with super().transaction(conversation_id):
            self.in_transaction = True
            try:
                yield self
            finally:
                self.in_transaction = False


class Issuer:
    def __init__(self, store: AccessStore, during_issue: Callable[[], None] | None = None) -> None:
        self.store = store
        self.during_issue = during_issue
        self.calls = 0
        self.reference: MediaObjectRef | None = None
        self.expiry: datetime | None = None

    async def upload_access(
        self, reference: MediaObjectRef, content_type: str, expires_at: datetime
    ) -> UploadAccess:
        assert not self.store.in_transaction
        assert reference.kind == MediaObjectKind.UPLOAD
        assert content_type == "image/png"
        self.calls += 1
        self.reference, self.expiry = reference, expires_at
        if self.during_issue is not None:
            self.during_issue()
        return UploadAccess(
            "https://s3.invalid/upload", (("policy", "opaque-synthetic-signature"),)
        )


async def test_upload_access_uses_two_authorizations_and_no_sql_during_issuance() -> None:
    store = AccessStore()
    source = image(store)
    store.sources = (ImagePreparationSource(source),)
    issuer = Issuer(store)
    result = await CreateChatImageUploadAccess(store, Sha256SessionHasher(), issuer)(
        CREDENTIAL, source.conversation_id, source.id
    )
    assert issuer.calls == 1
    assert issuer.reference == MediaObjectRef(source.id, MediaObjectKind.UPLOAD)
    assert issuer.expiry == source.upload_expires_at
    assert result.fields == (("policy", "opaque-synthetic-signature"),)
    assert "opaque-synthetic-signature" not in repr(result)
    assert store.sources[0].preparation == source


@pytest.mark.parametrize(
    "change", ["queued", "source", "session", "expiry", "revoked", "ban", "block"]
)
async def test_late_source_or_authority_change_does_not_return_the_signed_ticket(
    change: str,
) -> None:
    store = AccessStore()
    source = image(store)
    store.sources = (ImagePreparationSource(source),)

    def mutate() -> None:
        if change == "queued":
            store.sources = (ImagePreparationSource(source.queue(NOW)),)
        elif change == "source":
            altered = replace(source, source=replace(source.source, sha256=b"n" * 32))
            store.sources = (ImagePreparationSource(altered),)
        elif change == "session":
            store.actor = replace(store.actor, session=replace(store.actor.session, id=uuid4()))
        elif change == "expiry":
            store.clock = source.upload_expires_at
        elif change == "revoked":
            store.actor = replace(store.actor, session=replace(store.actor.session, revoked_at=NOW))
        elif change == "ban":
            store.actor = replace(store.actor, banned=True)
        else:
            assert store.access is not None
            store.access = replace(store.access, blocked=True)

    issuer = Issuer(store, mutate)
    error = (
        UnauthenticatedError
        if change == "revoked"
        else StudentActionDeniedError
        if change == "ban"
        else MessageContactUnavailableError
        if change == "block"
        else ChatImageUploadAccessDeniedError
    )
    with pytest.raises(error):
        await CreateChatImageUploadAccess(store, Sha256SessionHasher(), issuer)(
            CREDENTIAL, source.conversation_id, source.id
        )
    assert issuer.calls == 1


@pytest.mark.parametrize("unavailable", ["missing", "queued", "expired", "blocked"])
async def test_closed_or_unavailable_source_never_contacts_the_storage_issuer(
    unavailable: str,
) -> None:
    store = AccessStore()
    source = image(store)
    store.sources = (ImagePreparationSource(source),)
    if unavailable == "missing":
        store.sources = ()
    elif unavailable == "queued":
        store.sources = (ImagePreparationSource(source.queue(NOW)),)
    elif unavailable == "expired":
        store.clock = source.upload_expires_at
    else:
        assert store.access is not None
        store.access = replace(store.access, blocked=True)
    error = (
        ChatImageUnavailableError
        if unavailable == "missing"
        else MessageContactUnavailableError
        if unavailable == "blocked"
        else ChatImageUploadAccessDeniedError
    )
    issuer = Issuer(store)
    with pytest.raises(error):
        await CreateChatImageUploadAccess(store, Sha256SessionHasher(), issuer)(
            CREDENTIAL, source.conversation_id, source.id
        )
    assert issuer.calls == 0


async def test_storage_failure_propagates_without_advancing_preparation_state() -> None:
    store = AccessStore()
    source = image(store)
    store.sources = (ImagePreparationSource(source),)

    def fail() -> None:
        raise MediaStorageUnavailableError

    with pytest.raises(MediaStorageUnavailableError):
        await CreateChatImageUploadAccess(store, Sha256SessionHasher(), Issuer(store, fail))(
            CREDENTIAL, source.conversation_id, source.id
        )
    assert store.sources[0].preparation == source


async def test_session_expiring_while_loading_source_cannot_issue_transport() -> None:
    store = AccessStore()
    store.actor = replace(
        store.actor, session=replace(store.actor.session, expires_at=NOW + timedelta(minutes=1))
    )
    source = image(store)
    store.sources = (ImagePreparationSource(source),)
    store.final_expired = True
    issuer = Issuer(store)
    with pytest.raises(UnauthenticatedError):
        await CreateChatImageUploadAccess(store, Sha256SessionHasher(), issuer)(
            CREDENTIAL, source.conversation_id, source.id
        )
    assert issuer.calls == 0


class WrongSourceStore(AccessStore):
    async def image_source(
        self, account_id: UUID, conversation_id: UUID, image_id: UUID
    ) -> ImagePreparationSource | None:
        source = self.sources[0]
        assert source.preparation.account_id == account_id
        assert source.preparation.conversation_id == conversation_id
        assert source.preparation.id != image_id
        return source


async def test_misbound_requested_source_fails_closed_before_signing() -> None:
    store = WrongSourceStore()
    source = image(store)
    store.sources = (ImagePreparationSource(source),)
    issuer = Issuer(store)
    with pytest.raises(RuntimeError, match="actual requested image source"):
        await CreateChatImageUploadAccess(store, Sha256SessionHasher(), issuer)(
            CREDENTIAL, source.conversation_id, uuid4()
        )
    assert issuer.calls == 0
