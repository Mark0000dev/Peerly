import asyncio
from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.chat_images.finalize import FinalizeChatImage, FinalizeChatImageCommand
from studymate.application.chat_images.start import ChatImageMessageResolvedError
from studymate.application.idempotency import IntentKey
from studymate.application.messaging.commands import CancelMessageCommand, authorize_conversation
from studymate.domain.chat_images import ChatImagePreparation, ChatImageState
from studymate.domain.messaging import MessageOperation
from studymate.infrastructure.chat_images.finalize import SqlChatImageFinalizeUnitOfWork
from studymate.infrastructure.chat_images.models import ChatImageRecord, ChatImageRevisionRecord
from studymate.infrastructure.persistence.messaging import (
    SqlMessageTransaction,
    SqlMessageUnitOfWork,
)
from studymate.infrastructure.persistence.product_events import record_message_outcome
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.test_chat_image_cancellation import image_state
from tests.integration.test_message_commands import chat

pytestmark = pytest.mark.integration


async def test_finalize_cancel_race_always_leaves_a_retained_closed_source(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    image = await image_state(owned, "uploading")
    finalize = FinalizeChatImage(
        SqlChatImageFinalizeUnitOfWork(owned.api.sessions, record_message_outcome),
        HASHER,
        FINGERPRINTER,
    )
    finalization, cancellation = await asyncio.gather(
        finalize(
            FinalizeChatImageCommand(
                owned.sender.credential,
                image.conversation_id,
                image.id,
                IntentKey("racing-finalize"),
            )
        ),
        owned.cancel()(
            CancelMessageCommand(
                owned.sender.credential,
                image.conversation_id,
                image.client_message_id,
                IntentKey("racing-cancel"),
            )
        ),
        return_exceptions=True,
    )
    assert isinstance(cancellation, MessageOperation)
    assert cancellation.cancelled_at is not None
    assert isinstance(finalization, (ChatImagePreparation, ChatImageMessageResolvedError))
    if isinstance(finalization, ChatImageMessageResolvedError):
        assert finalization.operation == cancellation
    else:
        assert finalization.state == ChatImageState.QUEUED
    async with owned.api.sessions() as session:
        root = await session.get(ChatImageRecord, image.id)
        assert root is not None
        current = await session.get(ChatImageRevisionRecord, (image.id, root.current_version))
        assert current is not None
        assert current.state == "cancelled"


async def test_cleanup_rejects_a_real_confirmed_operation_without_touching_pending_images(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    image = await image_state(owned, "queued")
    confirmed = await owned.send()(owned.command())
    async with SqlMessageUnitOfWork(owned.api.sessions, record_message_outcome).transaction(
        image.conversation_id
    ) as transaction:
        await authorize_conversation(
            transaction, HASHER, owned.sender.credential, image.conversation_id
        )
        with pytest.raises(ValueError, match="Only a real cancelled message"):
            await transaction.cancel_image_preparation(confirmed)
    async with owned.api.sessions() as session:
        root = await session.get(ChatImageRecord, image.id)
        assert root is not None
        assert root.current_version == image.version


async def test_cancelling_another_text_intent_does_not_close_an_owned_image_intent(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    image = await image_state(owned, "queued")
    text = owned.command()
    outcome = await owned.cancel()(
        CancelMessageCommand(
            text.credential,
            text.conversation_id,
            text.client_message_id,
            IntentKey("cancel-other-text-intent"),
        )
    )
    assert outcome.cancelled_at is not None
    async with owned.api.sessions() as session:
        root = await session.get(ChatImageRecord, image.id)
        assert root is not None
        assert root.current_version == image.version


async def test_expired_upload_stays_expired_when_its_message_is_definitively_cancelled(
    identity_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owned = await chat(identity_engine)
    image = await image_state(owned, "uploading")

    async def elapsed(_transaction: SqlMessageTransaction) -> datetime:
        return image.upload_expires_at

    monkeypatch.setattr(SqlMessageTransaction, "now", elapsed)
    outcome = await owned.cancel()(
        CancelMessageCommand(
            owned.sender.credential,
            image.conversation_id,
            image.client_message_id,
            IntentKey("cancel-expired-upload"),
        )
    )
    assert outcome.cancelled_at == image.upload_expires_at
    async with owned.api.sessions() as session:
        root = await session.get(ChatImageRecord, image.id)
        assert root is not None
        current = await session.get(ChatImageRevisionRecord, (image.id, root.current_version))
        assert current is not None
        assert current.state == "expired"
