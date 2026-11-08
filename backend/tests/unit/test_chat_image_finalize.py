from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime
from typing import Self
from uuid import UUID, uuid4

import pytest

from studymate.application.chat_images.finalize import (
    ChatImageUnavailableError,
    FinalizeChatImage,
    FinalizeChatImageCommand,
)
from studymate.application.chat_images.start import ChatImageIntent, ChatImageMessageResolvedError
from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.messaging.ports import MessageContactUnavailableError
from studymate.domain.chat_images import ChatImagePreparation, ChatImageState
from studymate.domain.messaging import MessageOperation
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.chat_image_store import Store
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.test_chat_image_start import command, service


class FinalizeStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.final_intents: dict[IntentKey, ChatImageIntent] = {}

    @asynccontextmanager
    async def transaction(self, conversation_id: UUID) -> AsyncIterator[Self]:
        before = self.final_intents.copy()
        try:
            async with super().transaction(conversation_id):
                yield self
        except BaseException:
            self.final_intents = before
            raise

    async def image_finalize_intent(self, actor_id: UUID, key: IntentKey) -> ChatImageIntent | None:
        assert actor_id == self.actor.session.account_id
        if self.expire_after_replay:
            self.clock = self.actor.session.expires_at
        return self.final_intents.get(key)

    async def owned_image(
        self, actor_id: UUID, conversation_id: UUID, image_id: UUID
    ) -> ChatImagePreparation | None:
        return next(
            (
                image
                for image in self.images.values()
                if (image.account_id, image.conversation_id, image.id)
                == (actor_id, conversation_id, image_id)
            ),
            None,
        )

    async def save_image(self, image: ChatImagePreparation) -> None:
        self.images[image.client_message_id] = image

    async def remember_image_finalize(
        self, actor_id: UUID, key: IntentKey, intent: ChatImageIntent, at: datetime
    ) -> None:
        assert actor_id == intent.result.account_id
        assert at == self.clock
        self.final_intents[key] = intent
        if self.expire_after_write:
            self.clock = self.actor.session.expires_at


def finalize(store: FinalizeStore) -> FinalizeChatImage:
    return FinalizeChatImage(store, Sha256SessionHasher(), HmacIntentFingerprinter(b"f" * 32))


async def preparation(store: FinalizeStore) -> FinalizeChatImageCommand:
    image = await service(store)(command(store))
    return FinalizeChatImageCommand(
        CREDENTIAL, image.conversation_id, image.id, IntentKey("queue-image-once")
    )


async def test_finalize_queues_once_and_replays_immutable_receipt_without_sending() -> None:
    store = FinalizeStore()
    intent = await preparation(store)
    result = await finalize(store)(intent)
    assert result.state == ChatImageState.QUEUED
    assert store.operation is None
    processing = result.claim(uuid4(), NOW)
    store.images[result.client_message_id] = processing
    assert await finalize(store)(intent) == result
    assert (
        await finalize(store)(replace(intent, intent_key=IntentKey("different-finalize")))
        == processing
    )
    with pytest.raises(IdempotencyConflictError):
        await finalize(store)(replace(intent, image_id=uuid4()))
    assert store.operation is None


@pytest.mark.parametrize("reason", ["blocked", "banned", "deleted", "unverified"])
async def test_contact_change_denies_new_queue_but_preserves_original_receipt(reason: str) -> None:
    store = FinalizeStore()
    intent = await preparation(store)
    assert store.access is not None
    original = store.access
    store.access = replace(
        original,
        blocked=reason == "blocked",
        peer_banned=reason == "banned",
        peer_deleted=reason == "deleted",
        peer_verified=reason != "unverified",
    )
    with pytest.raises(MessageContactUnavailableError):
        await finalize(store)(intent)
    assert not store.final_intents
    store.access = original
    result = await finalize(store)(intent)
    store.access = replace(original, blocked=True)
    assert await finalize(store)(intent) == result


async def test_cancelled_message_cannot_be_revived_by_late_upload_finalization() -> None:
    store = FinalizeStore()
    intent = await preparation(store)
    image = next(iter(store.images.values()))
    assert store.access is not None
    store.operation = MessageOperation(
        uuid4(),
        intent.conversation_id,
        store.access.conversation.pair,
        image.account_id,
        image.client_message_id,
        cancelled_at=NOW,
    )
    with pytest.raises(ChatImageMessageResolvedError) as error:
        await finalize(store)(intent)
    assert error.value.operation is store.operation
    assert store.images[image.client_message_id].state == ChatImageState.UPLOADING
    assert not store.final_intents


async def test_missing_source_and_expired_postwrite_session_leave_no_finalization() -> None:
    store = FinalizeStore()
    intent = await preparation(store)
    with pytest.raises(ChatImageUnavailableError):
        await finalize(store)(replace(intent, image_id=uuid4()))
    store.expire_after_write = True
    with pytest.raises(UnauthenticatedError):
        await finalize(store)(intent)
    assert not store.final_intents
    assert next(iter(store.images.values())).state == ChatImageState.UPLOADING


async def test_elapsed_upload_deadline_is_retained_as_expired_not_queued() -> None:
    store = FinalizeStore()
    intent = await preparation(store)
    store.clock = next(iter(store.images.values())).upload_expires_at
    result = await finalize(store)(intent)
    assert result.state == ChatImageState.EXPIRED
    assert await finalize(store)(intent) == result


async def test_replay_requires_still_active_session_without_overwriting_receipt() -> None:
    store = FinalizeStore()
    intent = await preparation(store)
    await finalize(store)(intent)
    receipts = store.final_intents.copy()
    store.expire_after_replay = True
    with pytest.raises(UnauthenticatedError):
        await finalize(store)(intent)
    assert store.final_intents == receipts


async def test_corrupt_cross_conversation_receipt_cannot_escape_ownership_scope() -> None:
    store = FinalizeStore()
    intent = await preparation(store)
    result = await finalize(store)(intent)
    store.final_intents[intent.intent_key] = replace(
        store.final_intents[intent.intent_key],
        result=replace(result, conversation_id=uuid4()),
    )
    with pytest.raises(RuntimeError, match="unrelated owned source"):
        await finalize(store)(intent)


async def test_unrelated_message_outcome_is_not_treated_as_owned_cancellation() -> None:
    store = FinalizeStore()
    intent = await preparation(store)
    image = next(iter(store.images.values()))
    assert store.access is not None
    store.operation = MessageOperation(
        uuid4(),
        intent.conversation_id,
        store.access.conversation.pair,
        image.account_id,
        uuid4(),
        cancelled_at=NOW,
    )
    with pytest.raises(RuntimeError, match="unrelated message outcome"):
        await finalize(store)(intent)
    assert not store.final_intents
