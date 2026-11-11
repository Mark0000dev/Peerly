from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from studymate.application.chat_images.finalize import ChatImageUnavailableError
from studymate.application.chat_images.reads import (
    ImageMessageOutcome,
    ImagePreparationSource,
    ListOwnImagePreparations,
    ReadOwnedImagePreparation,
    ReadyImageInfo,
    owned_value,
)
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.domain.chat_images import ChatImagePreparation, ChatImageState
from studymate.domain.media import PhotoContentType, PhotoSource
from studymate.domain.messaging import MessageOutcome
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.chat_image_store import Store
from tests.unit.identity_store import CREDENTIAL, NOW


class ReadStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.sources: tuple[ImagePreparationSource, ...] = ()
        self.final_expired = False

    async def image_source(
        self, account_id: UUID, conversation_id: UUID, image_id: UUID
    ) -> ImagePreparationSource | None:
        assert account_id == self.actor.session.account_id
        assert self.access is not None
        assert conversation_id == self.access.conversation.id
        if self.final_expired:
            self.clock = self.actor.session.expires_at
        return next((source for source in self.sources if source.preparation.id == image_id), None)

    async def image_sources(
        self, account_id: UUID, conversation_id: UUID
    ) -> tuple[ImagePreparationSource, ...]:
        assert account_id == self.actor.session.account_id
        assert self.access is not None
        assert conversation_id == self.access.conversation.id
        if self.final_expired:
            self.clock = self.actor.session.expires_at
        return self.sources


def image(store: ReadStore) -> ChatImagePreparation:
    assert store.access is not None
    return ChatImagePreparation(
        uuid4(),
        store.actor.session.account_id,
        store.access.conversation.id,
        uuid4(),
        PhotoSource(100, b"p" * 32, PhotoContentType.PNG),
        NOW,
        NOW + timedelta(minutes=5),
        NOW + timedelta(minutes=15),
        NOW,
    )


def project(store: ReadStore, source: ImagePreparationSource, *, at_offset: int = 0) -> None:
    assert store.access is not None
    owned_value(
        source,
        store.actor.session.account_id,
        store.access.conversation.id,
        store.access.conversation.pair,
        NOW + timedelta(seconds=at_offset),
    )


@pytest.mark.parametrize(
    "state", [ChatImageState.UPLOADING, ChatImageState.QUEUED, ChatImageState.PROCESSING]
)
async def test_read_expiry_is_effective_only_and_not_a_new_revision(state: ChatImageState) -> None:
    store = ReadStore()
    original = image(store)
    if state != ChatImageState.UPLOADING:
        original = original.queue(NOW)
    if state == ChatImageState.PROCESSING:
        original = original.claim(uuid4(), NOW)
    store.sources = (ImagePreparationSource(original),)
    store.clock = (
        original.upload_expires_at
        if state == ChatImageState.UPLOADING
        else original.processing_expires_at
    )
    actual = await ReadOwnedImagePreparation(store, Sha256SessionHasher())(
        CREDENTIAL, original.conversation_id, original.id
    )
    assert actual.preparation is original
    assert actual.preparation.state == state
    assert actual.effective_state == ChatImageState.EXPIRED
    assert not store.images
    assert not store.intents
    assert "pppp" not in repr(actual)


async def test_ready_metadata_and_logical_cancel_are_separate_from_attachment_authority() -> None:
    store = ReadStore()
    assert store.access is not None
    original = image(store).queue(NOW).claim(uuid4(), NOW)
    assert original.attempt_id is not None
    original = original.ready(original.attempt_id, NOW)
    assert original.attempt_id is not None
    outcome = ImageMessageOutcome(
        uuid4(),
        store.access.conversation.pair,
        original.account_id,
        original.conversation_id,
        original.client_message_id,
        MessageOutcome.CANCELLED,
        None,
    )
    store.sources = (
        ImagePreparationSource(original, ReadyImageInfo(original.attempt_id, 10, 10, 100), outcome),
    )
    store.access = replace(store.access, blocked=True, peer_banned=True)
    result = await ListOwnImagePreparations(store, Sha256SessionHasher())(
        CREDENTIAL, original.conversation_id
    )
    assert result[0].effective_state == ChatImageState.READY
    assert result[0].message_outcome == outcome


@pytest.mark.parametrize("listing", [False, True])
async def test_final_session_deadline_is_enforced(listing: bool) -> None:
    store = ReadStore()
    original = image(store)
    store.sources = (ImagePreparationSource(original),)
    store.final_expired = True
    operation = (
        ListOwnImagePreparations(store, Sha256SessionHasher())(CREDENTIAL, original.conversation_id)
        if listing
        else ReadOwnedImagePreparation(store, Sha256SessionHasher())(
            CREDENTIAL, original.conversation_id, original.id
        )
    )
    with pytest.raises(UnauthenticatedError):
        await operation


async def test_missing_owned_source_is_unavailable() -> None:
    store = ReadStore()
    original = image(store)
    with pytest.raises(ChatImageUnavailableError):
        await ReadOwnedImagePreparation(store, Sha256SessionHasher())(
            CREDENTIAL, original.conversation_id, original.id
        )


@pytest.mark.parametrize("fault", ["owner", "future", "ready", "outcome"])
def test_projection_rejects_wrong_source_or_outcome(fault: str) -> None:
    store = ReadStore()
    original = image(store)
    ready = None
    outcome = None
    if fault == "owner":
        original = replace(original, account_id=uuid4())
    elif fault == "future":
        original = replace(original, updated_at=NOW + timedelta(seconds=1))
    elif fault == "ready":
        ready = ReadyImageInfo(uuid4(), 10, 10, 100)
    else:
        assert store.access is not None
        outcome = ImageMessageOutcome(
            uuid4(),
            store.access.conversation.pair,
            original.account_id,
            uuid4(),
            original.client_message_id,
            MessageOutcome.CANCELLED,
            None,
        )
    with pytest.raises(RuntimeError):
        project(store, ImagePreparationSource(original, ready, outcome))


@pytest.mark.parametrize("fault", ["pending", "terminal", "duplicate", "order"])
async def test_list_rejects_capacity_duplicate_or_order_corruption(fault: str) -> None:
    store = ReadStore()
    original = image(store)
    if fault == "pending":
        images = tuple(replace(original, id=uuid4()) for _ in range(4))
    elif fault == "terminal":
        images = tuple(replace(original.cancel(NOW), id=uuid4()) for _ in range(21))
    elif fault == "duplicate":
        images = (original, original)
    else:
        images = (replace(original, id=UUID(int=1)), replace(original, id=UUID(int=2)))
    store.sources = tuple(ImagePreparationSource(value) for value in images)
    with pytest.raises(RuntimeError):
        await ListOwnImagePreparations(store, Sha256SessionHasher())(
            CREDENTIAL, original.conversation_id
        )


def test_display_and_message_metadata_require_actual_shape() -> None:
    store = ReadStore()
    assert store.access is not None
    with pytest.raises(ValueError, match="actual"):
        ReadyImageInfo(uuid4(), 0, 10, 100)
    with pytest.raises(ValueError, match="actual"):
        ImageMessageOutcome(
            uuid4(),
            store.access.conversation.pair,
            uuid4(),
            uuid4(),
            uuid4(),
            MessageOutcome.CANCELLED,
            None,
        )
    with pytest.raises(ValueError, match="actual"):
        ImageMessageOutcome(
            uuid4(),
            store.access.conversation.pair,
            store.actor.session.account_id,
            uuid4(),
            uuid4(),
            MessageOutcome.CONFIRMED,
            None,
        )


def test_confirmed_logical_message_requires_exact_attachment_fk_to_match_preparation() -> None:
    store = ReadStore()
    assert store.access is not None
    original = image(store)
    outcome = ImageMessageOutcome(
        uuid4(),
        store.access.conversation.pair,
        original.account_id,
        original.conversation_id,
        original.client_message_id,
        MessageOutcome.CONFIRMED,
        uuid4(),
        original.id,
    )
    project(store, ImagePreparationSource(original, message_outcome=outcome))
    with pytest.raises(RuntimeError, match="attachment"):
        project(
            store,
            ImagePreparationSource(
                original, message_outcome=replace(outcome, message_image_id=uuid4())
            ),
        )
    with pytest.raises(ValueError, match="Cancelled"):
        replace(outcome, outcome=MessageOutcome.CANCELLED, message_id=None)
