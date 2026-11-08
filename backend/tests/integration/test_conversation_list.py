from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.idempotency import IntentKey
from studymate.application.messaging.conversation_list import (
    CONVERSATION_PAGE_SIZE,
    ListConversations,
)
from studymate.application.messaging.participants import ChatParticipantState
from studymate.application.messaging.read_positions import (
    AcknowledgeConversationRead,
    ReadPositionCommand,
)
from studymate.infrastructure.persistence.conversation_cursors import (
    FernetConversationListCursorCodec,
)
from studymate.infrastructure.persistence.conversation_list import SqlConversationListUnitOfWork
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.message_reads import SqlReadPositionUnitOfWork
from studymate.infrastructure.persistence.product_events import (
    record_conversation_read,
    record_message_outcome,
)
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.test_message_commands import chat

pytestmark = pytest.mark.integration


async def test_thread_list_has_real_acceptance_latest_sequence_and_private_incoming_count(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    listing = ListConversations(
        SqlConversationListUnitOfWork(owned.api.sessions),
        HASHER,
        FernetConversationListCursorCodec.from_key(b"a" * 32),
    )
    baseline = await listing(owned.sender.credential)
    assert len(baseline.conversations) == 1
    row = baseline.conversations[0]
    assert row.conversation_id == owned.conversation_id
    assert row.last_message is None
    assert row.activity_at == row.accepted_at
    assert row.unread_count == 0
    assert row.can_send
    assert row.peer.state == ChatParticipantState.AVAILABLE
    outgoing = await owned.send()(owned.command())
    incoming = await owned.send()(owned.command(owned.recipient))
    assert outgoing.message is not None
    assert incoming.message is not None
    sender = (await listing(owned.sender.credential)).conversations[0]
    recipient = (await listing(owned.recipient.credential)).conversations[0]
    assert sender.last_message == incoming.message
    assert recipient.last_message == incoming.message
    assert sender.unread_count == 1
    assert recipient.unread_count == 1
    assert sender.original_context == row.original_context
    marker = await AcknowledgeConversationRead(
        SqlReadPositionUnitOfWork(
            owned.api.sessions, record_message_outcome, record_conversation_read
        ),
        HASHER,
        FINGERPRINTER,
    )(
        ReadPositionCommand(
            owned.sender.credential,
            owned.conversation_id,
            incoming.message.sequence,
            IntentKey(str(uuid4())),
        )
    )
    after = (await listing(owned.sender.credential)).conversations[0]
    assert after.unread_count == 0
    assert after.activity_at == sender.activity_at
    assert after.last_message == incoming.message
    assert (await listing(owned.recipient.credential)).conversations[0].unread_count == 1
    assert marker.account_id == owned.sender.id


@pytest.mark.parametrize("state", ["deleted", "banned"])
async def test_thread_list_retains_history_and_original_context_but_masks_unavailable_peer(
    identity_engine: AsyncEngine,
    state: str,
) -> None:
    owned = await chat(identity_engine)
    sent = await owned.send()(owned.command())
    assert sent.message is not None
    listing = ListConversations(
        SqlConversationListUnitOfWork(owned.api.sessions),
        HASHER,
        FernetConversationListCursorCodec.from_key(b"a" * 32),
    )
    before = (await listing(owned.sender.credential)).conversations[0]
    async with owned.api.sessions.begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == owned.recipient.id)
            .values(
                {
                    AccountRecord.deleted_at
                    if state == "deleted"
                    else AccountRecord.banned_at: func.clock_timestamp()
                }
            )
        )
    after = (await listing(owned.sender.credential)).conversations[0]
    assert after.last_message == sent.message
    assert after.original_context == before.original_context
    assert after.peer.name is None
    assert after.peer.photo_version is None
    assert after.peer.state == (
        ChatParticipantState.DELETED if state == "deleted" else ChatParticipantState.UNAVAILABLE
    )
    assert not after.can_send
    assert replace(after, peer=before.peer, can_send=before.can_send) == before


async def test_actual_twenty_plus_lookahead_pages_have_constant_query_count_and_no_foreign_thread(
    identity_engine: AsyncEngine,
) -> None:
    from sqlalchemy import event

    from studymate.application.profiles.goals import ReadOwnGoal
    from studymate.infrastructure.persistence.goals import SqlGoalUnitOfWork
    from tests.integration.requests.fixture import action, additional_peer, sent

    owned = await chat(identity_engine)
    listing = ListConversations(
        SqlConversationListUnitOfWork(owned.api.sessions),
        HASHER,
        FernetConversationListCursorCodec.from_key(b"a" * 32),
    )
    statements: list[str] = []

    def capture(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _many: bool,
    ) -> None:
        statements.append(statement)

    event.listen(identity_engine.sync_engine, "before_cursor_execute", capture)
    try:
        await listing(owned.sender.credential)
        single_count = len(statements)
    finally:
        event.remove(identity_engine.sync_engine, "before_cursor_execute", capture)
    goal = await ReadOwnGoal(SqlGoalUnitOfWork(owned.api.sessions), HASHER)(owned.sender.credential)
    assert goal is not None
    subject_id = goal.goal.content.canonical_subject_id
    assert subject_id is not None
    expected = {owned.conversation_id}
    for _ in range(CONVERSATION_PAGE_SIZE):
        peer = await additional_peer(identity_engine, subject_id)
        request = await sent(owned.api, peer, owned.sender)
        accepted = await owned.api.accept(action(owned.sender, peer, request))
        expected.add(accepted.conversation.id)
    statements.clear()
    event.listen(identity_engine.sync_engine, "before_cursor_execute", capture)
    try:
        first = await listing(owned.sender.credential)
    finally:
        event.remove(identity_engine.sync_engine, "before_cursor_execute", capture)
    assert len(statements) == single_count
    assert len(first.conversations) == CONVERSATION_PAGE_SIZE
    assert first.next_cursor is not None
    late = await owned.send()(owned.command())
    assert late.message is not None
    last = await listing(owned.sender.credential, first.next_cursor)
    assert len(last.conversations) == 1
    assert last.next_cursor is None
    assert last.conversations[0].last_message is None
    fresh = await listing(owned.sender.credential)
    assert fresh.conversations[0].last_message == late.message
    assert {row.conversation_id for row in (*first.conversations, *last.conversations)} == expected
    foreign = await listing(owned.recipient.credential)
    assert {row.conversation_id for row in foreign.conversations} == {owned.conversation_id}


async def test_thread_preview_uses_confirmed_sequence_even_if_last_message_clock_moves_backwards(
    identity_engine: AsyncEngine,
) -> None:
    from datetime import timedelta

    from studymate.infrastructure.persistence.message_models import MessageRecord

    owned = await chat(identity_engine)
    first = await owned.send()(owned.command())
    last = await owned.send()(owned.command())
    assert first.message is not None
    assert last.message is not None
    earlier = first.message.sent_at - timedelta(minutes=1)
    async with owned.api.sessions.begin() as session:
        await session.execute(
            update(MessageRecord).where(MessageRecord.id == last.message.id).values(sent_at=earlier)
        )
    listing = ListConversations(
        SqlConversationListUnitOfWork(owned.api.sessions),
        HASHER,
        FernetConversationListCursorCodec.from_key(b"a" * 32),
    )
    result = (await listing(owned.recipient.credential)).conversations[0]
    assert result.last_message == replace(last.message, sent_at=earlier)
    assert result.activity_at == first.message.sent_at
    assert result.unread_count == last.message.sequence


async def test_manual_hide_and_completed_goal_do_not_remove_an_accepted_thread_or_current_name(
    identity_engine: AsyncEngine,
) -> None:
    from studymate.application.profiles.goals import (
        CompleteGoalCommand,
        CompleteOwnGoal,
        ReadOwnGoal,
    )
    from studymate.infrastructure.persistence.goals import SqlGoalUnitOfWork
    from tests.integration.profile_lifecycle_fixture import command, services

    owned = await chat(identity_engine)
    listing = ListConversations(
        SqlConversationListUnitOfWork(owned.api.sessions),
        HASHER,
        FernetConversationListCursorCodec.from_key(b"a" * 32),
    )
    before = (await listing(owned.sender.credential)).conversations[0]
    visibility, _ = services(identity_engine)
    await visibility(command(owned.recipient))
    goal_uow = SqlGoalUnitOfWork(owned.api.sessions)
    goal = await ReadOwnGoal(goal_uow, HASHER)(owned.recipient.credential)
    assert goal is not None
    await CompleteOwnGoal(goal_uow, HASHER, FINGERPRINTER)(
        CompleteGoalCommand(
            owned.recipient.credential,
            goal.goal.id,
            goal.goal.version,
            IntentKey(str(uuid4())),
        )
    )
    after = (await listing(owned.sender.credential)).conversations[0]
    assert after == before
    sent = await owned.send()(owned.command())
    assert sent.message is not None
