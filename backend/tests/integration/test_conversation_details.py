from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.idempotency import IntentKey
from studymate.application.messaging.conversation_details import ReadConversationDetails
from studymate.application.messaging.read_positions import (
    AcknowledgeConversationRead,
    ReadPositionCommand,
)
from studymate.infrastructure.persistence.conversation_details import (
    SqlConversationDetailsUnitOfWork,
)
from studymate.infrastructure.persistence.discovery_freshness_models import DiscoveryExposureRecord
from studymate.infrastructure.persistence.message_reads import SqlReadPositionUnitOfWork
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import (
    record_conversation_read,
    record_message_outcome,
)
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.test_message_commands import chat

pytestmark = pytest.mark.integration


async def test_actual_details_keep_original_context_and_private_unread_without_implicit_ack(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    uow = SqlConversationDetailsUnitOfWork(
        owned.api.sessions, record_message_outcome, record_conversation_read
    )
    read = ReadConversationDetails(uow, HASHER)
    initial = await read(owned.recipient.credential, owned.conversation_id)
    assert initial.read_position is None
    assert initial.unread_count == 0
    assert initial.accepted_request.conversation_id == owned.conversation_id
    assert initial.conversation.next_message_sequence == 1
    await owned.send()(owned.command())
    last = await owned.send()(owned.command())
    assert last.message is not None
    unread = await read(owned.recipient.credential, owned.conversation_id)
    assert unread.unread_count == last.message.sequence
    own = await read(owned.sender.credential, owned.conversation_id)
    assert own.unread_count == 0
    assert own.read_position is None
    write_uow = SqlReadPositionUnitOfWork(
        owned.api.sessions, record_message_outcome, record_conversation_read
    )
    position = await AcknowledgeConversationRead(write_uow, HASHER, FINGERPRINTER)(
        ReadPositionCommand(
            owned.recipient.credential, owned.conversation_id, 1, IntentKey(str(uuid4()))
        )
    )
    async with owned.api.sessions() as session:
        activity = {
            row.account_id: row.last_activity_at
            for row in await session.scalars(select(DiscoveryExposureRecord))
        }
        events = frozenset(await session.scalars(select(ProductEventRecord.id)))
    current = await read(owned.recipient.credential, owned.conversation_id)
    assert current.read_position == position
    assert current.unread_count == 1
    assert current.accepted_request == initial.accepted_request
    assert (await read(owned.sender.credential, owned.conversation_id)).read_position is None
    async with owned.api.sessions() as session:
        assert {
            row.account_id: row.last_activity_at
            for row in await session.scalars(select(DiscoveryExposureRecord))
        } == activity
        assert frozenset(await session.scalars(select(ProductEventRecord.id))) == events
