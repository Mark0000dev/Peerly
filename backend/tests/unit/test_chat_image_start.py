from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from studymate.application.chat_images.start import (
    ChatImageMessageResolvedError,
    ChatImageRateLimitedError,
    ChatImageSourceConflictError,
    StartChatImage,
    StartChatImageCommand,
)
from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.application.media.uploads import UploadBudget
from studymate.application.messaging.ports import (
    ConversationUnavailableError,
    MessageContactUnavailableError,
)
from studymate.domain.chat_images import ChatImageState
from studymate.domain.media import PhotoContentType, PhotoSource
from studymate.domain.messaging import MessageOperation
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.chat_image_store import Store
from tests.unit.identity_store import CREDENTIAL, NOW


def command(store: Store) -> StartChatImageCommand:
    assert store.access is not None
    return StartChatImageCommand(
        CREDENTIAL,
        store.access.conversation.id,
        uuid4(),
        PhotoSource(100, b"p" * 32, PhotoContentType.PNG),
        IntentKey("first-image-start"),
    )


def service(store: Store) -> StartChatImage:
    return StartChatImage(store, Sha256SessionHasher(), HmacIntentFingerprinter(b"k" * 32))


async def test_start_replay_keeps_original_receipt_and_same_client_never_spends_another_start() -> (
    None
):
    store = Store()
    intent = command(store)
    result = await service(store)(intent)
    assert result.source is intent.source
    assert result.state == ChatImageState.UPLOADING
    assert result.client_message_id == intent.client_message_id
    assert result.conversation_id == intent.conversation_id
    assert result.account_id == store.actor.session.account_id
    store.images[intent.client_message_id] = result.queue(NOW)
    assert await service(store)(intent) == result
    assert await service(store)(
        replace(intent, intent_key=IntentKey("new-image-transport"))
    ) == result.queue(NOW)
    assert len(store.images) == 1
    assert store.capacity_checks == 1
    with pytest.raises(IdempotencyConflictError):
        await service(store)(replace(intent, source=replace(intent.source, sha256=b"q" * 32)))
    with pytest.raises(ChatImageSourceConflictError):
        await service(store)(
            replace(
                intent,
                source=replace(intent.source, sha256=b"q" * 32),
                intent_key=IntentKey("changed-image-bytes"),
            )
        )


@pytest.mark.parametrize("reason", ["blocked", "banned", "deleted", "unverified"])
async def test_contact_guard_prevents_new_preparation_but_not_original_owned_receipt(
    reason: str,
) -> None:
    store = Store()
    intent = command(store)
    prior = await service(store)(intent)
    assert store.access is not None
    store.access = replace(
        store.access,
        blocked=reason == "blocked",
        peer_banned=reason == "banned",
        peer_deleted=reason == "deleted",
        peer_verified=reason != "unverified",
    )
    assert await service(store)(intent) == prior
    with pytest.raises(MessageContactUnavailableError):
        await service(store)(
            replace(intent, client_message_id=uuid4(), intent_key=IntentKey("new-peer-image"))
        )
    assert len(store.images) == 1


@pytest.mark.parametrize("state", ["unverified", "unactivated", "banned", "deleted"])
async def test_live_student_authority_is_required_before_image_admission(state: str) -> None:
    store = Store()
    intent = command(store)
    store.actor = replace(
        store.actor,
        membership=None if state == "unverified" else store.actor.membership,
        activation_complete=state != "unactivated",
        banned=state == "banned",
        deleted_at=NOW if state == "deleted" else None,
    )
    expected = UnauthenticatedError if state == "deleted" else StudentActionDeniedError
    with pytest.raises(expected):
        await service(store)(intent)
    assert not store.images
    assert not store.intents


async def test_missing_conversation_and_expiry_after_write_leave_no_admission() -> None:
    store = Store()
    intent = command(store)
    access = store.access
    store.access = None
    with pytest.raises(ConversationUnavailableError):
        await service(store)(intent)
    store.access = access
    store.expire_after_write = True
    with pytest.raises(UnauthenticatedError):
        await service(store)(intent)
    assert not store.images
    assert not store.intents


async def test_terminal_message_cancellation_prevents_late_image_start_without_new_source() -> None:
    store = Store()
    intent = command(store)
    assert store.access is not None
    store.operation = MessageOperation(
        uuid4(),
        intent.conversation_id,
        store.access.conversation.pair,
        store.actor.session.account_id,
        intent.client_message_id,
        cancelled_at=NOW,
    )
    with pytest.raises(ChatImageMessageResolvedError) as error:
        await service(store)(intent)
    assert error.value.operation is store.operation
    assert not store.images
    assert not store.intents


@pytest.mark.parametrize("mode", ["starts", "pending", "both"])
async def test_capacity_uses_actual_retained_retry_deadlines_and_never_creates_an_image(
    mode: str,
) -> None:
    store = Store()
    store.budget = UploadBudget(
        20 if mode in {"starts", "both"} else 0,
        NOW - timedelta(minutes=30),
        3 if mode in {"pending", "both"} else 0,
        NOW + timedelta(minutes=10),
    )
    with pytest.raises(ChatImageRateLimitedError) as error:
        await service(store)(command(store))
    assert error.value.retry_at == NOW + timedelta(minutes=10 if mode == "pending" else 30)
    assert not store.images
    assert not store.intents


@pytest.mark.parametrize(
    "budget",
    [
        UploadBudget(20, None, 0, None),
        UploadBudget(0, None, 3, None),
        UploadBudget(20, NOW - timedelta(hours=1), 0, None),
    ],
)
async def test_inconsistent_capacity_facts_fail_closed_instead_of_guessing_retry_time(
    budget: UploadBudget,
) -> None:
    store = Store()
    store.budget = budget
    with pytest.raises(RuntimeError):
        await service(store)(command(store))
    assert not store.images


async def test_replay_rechecks_session_and_rejects_foreign_preparation_source() -> None:
    store = Store()
    intent = command(store)
    image = await service(store)(intent)
    store.images[intent.client_message_id] = replace(image, account_id=UUID(int=99))
    with pytest.raises(RuntimeError, match="another message intent"):
        await service(store)(replace(intent, intent_key=IntentKey("foreign-image-result")))
    store.expire_after_replay = True
    with pytest.raises(UnauthenticatedError):
        await service(store)(intent)


async def test_unrelated_terminal_projection_cannot_be_returned_as_owned_image_status() -> None:
    store = Store()
    intent = command(store)
    assert store.access is not None
    store.operation = MessageOperation(
        uuid4(),
        intent.conversation_id,
        store.access.conversation.pair,
        UUID(int=3),
        intent.client_message_id,
        cancelled_at=NOW,
    )
    with pytest.raises(RuntimeError, match="unrelated message outcome"):
        await service(store)(intent)
    assert not store.images
    assert not store.intents
