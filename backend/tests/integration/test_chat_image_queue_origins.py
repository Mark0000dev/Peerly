from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.chat_images.finalize import FinalizeChatImage, FinalizeChatImageCommand
from studymate.application.idempotency import IntentKey
from studymate.infrastructure.chat_images.finalize import SqlChatImageFinalizeUnitOfWork
from studymate.infrastructure.chat_images.origins import (
    ChatImageQueueOriginRecord,
    read_image_queue_origin,
)
from studymate.infrastructure.observability.origin import ExecutionOrigin
from studymate.infrastructure.persistence.product_events import record_message_outcome
from tests.image_fixture import encoded
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.test_chat_image_worker import queued

pytestmark = pytest.mark.integration


async def test_first_actual_queue_origin_survives_later_finalize_intents_and_replays(
    identity_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = ExecutionOrigin(uuid4(), uuid4(), "1" * 32, "2" * 16)
    current = first
    monkeypatch.setattr(
        "studymate.infrastructure.chat_images.origins.current_origin", lambda: current
    )
    owned, image = await queued(identity_engine, encoded())
    current = replace(first, request_id=uuid4(), action_id=uuid4())
    finalize = FinalizeChatImage(
        SqlChatImageFinalizeUnitOfWork(owned.api.sessions, record_message_outcome),
        HASHER,
        FINGERPRINTER,
    )
    command = FinalizeChatImageCommand(
        owned.sender.credential, image.conversation_id, image.id, IntentKey("later-finalize-origin")
    )
    assert await finalize(command) == image
    assert await finalize(command) == image
    async with owned.api.sessions() as session:
        assert await read_image_queue_origin(session, image.id) == first
        row = await session.get(ChatImageQueueOriginRecord, image.id)
        assert row is not None
        assert row.version == image.version
        assert row.recorded_at == image.updated_at
        assert row.account_id == image.account_id
        assert row.conversation_id == image.conversation_id
        assert row.client_message_id == image.client_message_id
        assert row.state == "queued"


async def test_missing_actual_execution_origin_is_not_inferred_from_finalize_receipts(
    identity_engine: AsyncEngine,
) -> None:
    owned, image = await queued(identity_engine, encoded())
    async with owned.api.sessions() as session:
        assert await read_image_queue_origin(session, image.id) is None
        assert tuple(await session.scalars(select(ChatImageQueueOriginRecord))) == ()


@pytest.mark.parametrize("invalid", ["owner", "version", "state", "trace", "span"])
async def test_queue_origin_fk_and_trace_constraints_reject_false_source_links(
    identity_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch, invalid: str
) -> None:
    origin = ExecutionOrigin(uuid4(), None, None, None)
    monkeypatch.setattr(
        "studymate.infrastructure.chat_images.origins.current_origin", lambda: origin
    )
    owned, image = await queued(identity_engine, encoded())
    statement = update(ChatImageQueueOriginRecord).where(
        ChatImageQueueOriginRecord.image_id == image.id
    )
    if invalid == "owner":
        statement = statement.values(account_id=owned.recipient.id)
    elif invalid == "version":
        statement = statement.values(version=image.version + 1)
    elif invalid == "state":
        statement = statement.values(state="uploading")
    elif invalid == "trace":
        statement = statement.values(trace_id="0" * 32, span_id="2" * 16)
    else:
        statement = statement.values(trace_id="1" * 32, span_id=None)
    async with owned.api.sessions() as session:
        with pytest.raises(IntegrityError):
            await session.execute(statement)
    async with owned.api.sessions() as session:
        assert await read_image_queue_origin(session, image.id) == origin
