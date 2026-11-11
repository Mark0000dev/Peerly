from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.discovery.profiles import ReadDiscoveryProfile
from studymate.application.idempotency import IntentKey
from studymate.application.messaging.history import ReadMessageHistory
from studymate.application.messaging.history_ports import MESSAGE_HISTORY_PAGE_SIZE
from studymate.application.messaging.ports import ConversationUnavailableError
from studymate.application.safety.blocks import ChangeBlockCommand, ChangeOwnBlock
from studymate.infrastructure.messaging.cursors import FernetMessageHistoryCursorCodec
from studymate.infrastructure.messaging.history import SqlMessageHistoryUnitOfWork
from studymate.infrastructure.persistence.blocks import SqlBlockUnitOfWork
from studymate.infrastructure.persistence.conversation_models import ConversationRecord
from studymate.infrastructure.persistence.discovery_profiles import SqlDiscoveryProfileUnitOfWork
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_message_outcome
from tests.integration.onboarding_fixture import ready_setup
from tests.integration.profile_lifecycle_fixture import command as visibility_command
from tests.integration.profile_lifecycle_fixture import complete_existing_setup
from tests.integration.profile_lifecycle_fixture import services as visibility_services
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.student_actor import actor
from tests.integration.test_message_commands import chat

pytestmark = pytest.mark.integration


async def test_bounded_actual_history_is_sequence_ordered_with_fixed_anchor_and_no_ack_side_effect(
    identity_engine: AsyncEngine,
) -> None:
    context = await chat(identity_engine)
    send = context.send()
    for _ in range(MESSAGE_HISTORY_PAGE_SIZE + 1):
        await send(context.command())
    read = ReadMessageHistory(
        SqlMessageHistoryUnitOfWork(context.api.sessions, record_message_outcome),
        HASHER,
        FernetMessageHistoryCursorCodec.from_key(b"x" * 32),
    )
    first = await read(context.sender.credential, context.conversation_id)
    assert [message.sequence for message in first.messages] == list(
        range(2, MESSAGE_HISTORY_PAGE_SIZE + 2)
    )
    assert first.next_cursor is not None
    last = await send(context.command())
    assert last.message is not None
    async with context.api.sessions() as session:
        before = await session.scalar(select(func.count()).select_from(ProductEventRecord))
    second = await read(context.sender.credential, context.conversation_id, first.next_cursor)
    assert [message.sequence for message in second.messages] == [1]
    assert second.anchor_sequence == first.anchor_sequence
    assert second.next_cursor is None
    assert last.message.id not in {message.id for message in second.messages}
    async with context.api.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ProductEventRecord)) == before
        conversation = await session.get(ConversationRecord, context.conversation_id)
        assert conversation is not None
        assert conversation.next_message_sequence == last.message.sequence + 1


async def test_empty_foreign_and_unknown_history_use_actual_membership_scope(
    identity_engine: AsyncEngine,
) -> None:
    context = await chat(identity_engine)
    read = ReadMessageHistory(
        SqlMessageHistoryUnitOfWork(context.api.sessions, record_message_outcome),
        HASHER,
        FernetMessageHistoryCursorCodec.from_key(b"x" * 32),
    )
    page = await read(context.sender.credential, context.conversation_id)
    assert page.messages == ()
    assert page.anchor_sequence == 0
    assert page.next_cursor is None
    other = await actor(identity_engine)
    await ready_setup(identity_engine, other.credential)
    await complete_existing_setup(identity_engine, other)
    for conversation_id in (context.conversation_id, uuid4()):
        with pytest.raises(ConversationUnavailableError):
            await read(other.credential, conversation_id)


async def test_peer_hide_block_and_delete_preserve_actual_accepted_history(
    identity_engine: AsyncEngine,
) -> None:
    context = await chat(identity_engine)
    operation = await context.send()(context.command())
    read = ReadMessageHistory(
        SqlMessageHistoryUnitOfWork(context.api.sessions, record_message_outcome),
        HASHER,
        FernetMessageHistoryCursorCodec.from_key(b"x" * 32),
    )
    profile = await ReadDiscoveryProfile(
        SqlDiscoveryProfileUnitOfWork(context.api.sessions), HASHER
    )(context.recipient.credential, context.sender.id)
    visibility, _ = visibility_services(identity_engine)
    await visibility(visibility_command(context.recipient))
    assert (await read(context.sender.credential, context.conversation_id)).messages == (
        operation.message,
    )
    block = ChangeOwnBlock(SqlBlockUnitOfWork(context.api.sessions), HASHER, FINGERPRINTER)
    await block(
        ChangeBlockCommand(
            context.recipient.credential,
            context.sender.id,
            True,
            0,
            IntentKey(str(uuid4())),
            profile.access_context.id,
        )
    )
    assert (await read(context.sender.credential, context.conversation_id)).messages == (
        operation.message,
    )
    # Controlled lifecycle fixture, not an invented public deletion permission.
    async with context.api.sessions.begin() as session:
        at = await SqlIdentityTransaction(session).now()
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == context.recipient.id)
            .values(deleted_at=at)
        )
    assert (await read(context.sender.credential, context.conversation_id)).messages == (
        operation.message,
    )
