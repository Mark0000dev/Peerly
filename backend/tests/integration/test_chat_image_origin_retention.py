from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from studymate.application.chat_images.finalize import FinalizeChatImage, FinalizeChatImageCommand
from studymate.application.idempotency import IntentKey
from studymate.domain.chat_images import ChatImagePreparation
from studymate.infrastructure.chat_images.finalize import SqlChatImageFinalizeUnitOfWork
from studymate.infrastructure.chat_images.models import (
    ChatImageIntentRecord,
    ChatImageRecord,
    ChatImageRevisionRecord,
)
from studymate.infrastructure.chat_images.origins import ChatImageQueueOriginRecord
from studymate.infrastructure.observability.origin import ExecutionOrigin
from studymate.infrastructure.persistence.product_events import record_message_outcome
from tests.image_fixture import encoded
from tests.integration.migrations import run_revision_step
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.test_chat_image_start import start, submission
from tests.integration.test_chat_image_worker import queued
from tests.integration.test_message_commands import chat

pytestmark = pytest.mark.integration


async def test_queue_execution_origin_survives_refused_downgrade(
    identity_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = ExecutionOrigin(uuid4(), None, None, None)
    monkeypatch.setattr(
        "studymate.infrastructure.chat_images.origins.current_origin", lambda: source
    )
    owned, image = await queued(identity_engine, encoded())
    with pytest.raises(
        RuntimeError, match="Refusing to drop retained image queue execution origins"
    ):
        async with identity_engine.begin() as connection:
            await connection.run_sync(
                run_revision_step, "0044_chat_image_queue_origins", "downgrade"
            )
    async with owned.api.sessions() as session:
        retained = await session.get(ChatImageQueueOriginRecord, image.id)
        assert retained is not None
        assert retained.request_id == source.request_id


async def test_origin_failure_rolls_back_queue_revision_and_finalize_receipt(
    identity_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    owned = await chat(identity_engine)
    image = await start(owned)(submission(owned))

    async def fail_origin(_session: AsyncSession, _image: ChatImagePreparation) -> None:
        raise RuntimeError("controlled origin persistence failure")

    monkeypatch.setattr(
        "studymate.infrastructure.chat_images.finalize.remember_image_queue_origin", fail_origin
    )
    finalize = FinalizeChatImage(
        SqlChatImageFinalizeUnitOfWork(owned.api.sessions, record_message_outcome),
        HASHER,
        FINGERPRINTER,
    )
    with pytest.raises(RuntimeError, match="controlled origin persistence failure"):
        await finalize(
            FinalizeChatImageCommand(
                owned.sender.credential,
                image.conversation_id,
                image.id,
                IntentKey("origin-rollback-finalize"),
            )
        )
    async with owned.api.sessions() as session:
        root = await session.get(ChatImageRecord, image.id)
        assert root is not None
        assert root.current_version == image.version
        revision = await session.get(ChatImageRevisionRecord, (image.id, root.current_version))
        assert revision is not None
        assert revision.state == "uploading"
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ChatImageIntentRecord)
                .where(ChatImageIntentRecord.operation == "finalize")
            )
            == 0
        )
        assert await session.get(ChatImageQueueOriginRecord, image.id) is None
