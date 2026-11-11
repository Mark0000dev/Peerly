from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.idempotency import IntentKey
from studymate.application.messaging.commands import CancelMessageCommand
from studymate.application.messaging.read_positions import (
    AcknowledgeConversationRead,
    ReadPositionCommand,
)
from studymate.domain.changes import ChangeResource
from studymate.infrastructure.changes.sources import project_change_hints
from studymate.infrastructure.persistence.message_reads import SqlReadPositionUnitOfWork
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import (
    record_conversation_read,
    record_message_outcome,
)
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.test_message_commands import chat

pytestmark = pytest.mark.integration


async def test_actual_private_message_cancel_and_read_sources_project_only_safe_owned_hints(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    message = await owned.send()(owned.command())
    assert message.message is not None
    await owned.cancel()(
        CancelMessageCommand(
            owned.sender.credential,
            owned.conversation_id,
            uuid4(),
            IntentKey(str(uuid4())),
        )
    )
    await AcknowledgeConversationRead(
        SqlReadPositionUnitOfWork(
            owned.api.sessions, record_message_outcome, record_conversation_read
        ),
        HASHER,
        FINGERPRINTER,
    )(
        ReadPositionCommand(
            owned.recipient.credential,
            owned.conversation_id,
            message.message.sequence,
            IntentKey(str(uuid4())),
        )
    )
    async with owned.api.sessions() as session:
        events = tuple(await session.scalars(select(ProductEventRecord)))
        projected = await project_change_hints(session, events)
    by_kind = {event.kind: projected[event.id] for event in events}
    assert {hint.recipient_id for hint in by_kind["message.confirmed"]} == {
        owned.sender.id,
        owned.recipient.id,
    }
    assert {hint.recipient_id for hint in by_kind["message.cancelled"]} == {owned.sender.id}
    assert {hint.recipient_id for hint in by_kind["conversation.read_acknowledged"]} == {
        owned.recipient.id
    }
    assert {hint.recipient_id for hint in by_kind["request.changed"]} == {
        owned.sender.id,
        owned.recipient.id,
    }
    for event in events:
        hints = projected[event.id]
        assert len({hint.recipient_id for hint in hints}) == len(hints)
        for hint in hints:
            assert hint.canonical_event_id == event.id
            assert hint.recipient_id in {owned.sender.id, owned.recipient.id}
            assert "Synthetic private message" not in repr(hint)
            assert "Explicit synthetic reviewed text" not in repr(hint)
        if event.kind in {
            "message.confirmed",
            "message.cancelled",
            "conversation.read_acknowledged",
        }:
            assert all(hint.resource_type == ChangeResource.CONVERSATION for hint in hints)
            assert all(hint.resource_id == owned.conversation_id for hint in hints)
        if event.kind == "goal.saved":
            assert len(hints) == 1
            assert hints[0].resource_type == ChangeResource.ACCOUNT
            assert hints[0].resource_id == event.account_id


async def test_empty_change_source_batch_performs_no_source_reads(
    identity_engine: AsyncEngine,
) -> None:
    from sqlalchemy import event

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
        owned = await chat(identity_engine)
        statements.clear()
        async with owned.api.sessions() as session:
            assert await project_change_hints(session, ()) == {}
        assert not statements
    finally:
        event.remove(identity_engine.sync_engine, "before_cursor_execute", capture)


async def test_goal_share_and_block_hints_do_not_disclose_block_reason_or_operator_inspection(
    identity_engine: AsyncEngine,
) -> None:
    from studymate.application.discovery.profiles import ReadDiscoveryProfile
    from studymate.application.safety.blocks import ChangeBlockCommand, ChangeOwnBlock
    from studymate.infrastructure.persistence.blocks import SqlBlockUnitOfWork
    from studymate.infrastructure.persistence.discovery_profiles import (
        SqlDiscoveryProfileUnitOfWork,
    )
    from studymate.infrastructure.persistence.product_events import record_operator_audit
    from tests.integration.messaging.goal_share_fixture import command, sharing
    from tests.integration.test_operator_event_schema import seeded_audit

    owned = await chat(identity_engine)
    await sharing(owned).share(await command(owned))
    profile = await ReadDiscoveryProfile(SqlDiscoveryProfileUnitOfWork(owned.api.sessions), HASHER)(
        owned.sender.credential, owned.recipient.id
    )
    await ChangeOwnBlock(SqlBlockUnitOfWork(owned.api.sessions), HASHER, FINGERPRINTER)(
        ChangeBlockCommand(
            owned.sender.credential,
            owned.recipient.id,
            True,
            0,
            IntentKey(str(uuid4())),
            profile.access_context.id,
        )
    )
    audit = await seeded_audit(identity_engine)
    async with owned.api.sessions.begin() as session:
        await record_operator_audit(session, audit)
    async with owned.api.sessions() as session:
        events = tuple(await session.scalars(select(ProductEventRecord)))
        projection = await project_change_hints(session, events)
    by_kind = {event.kind: projection[event.id] for event in events}
    assert {hint.recipient_id for hint in by_kind["conversation.goal_shared"]} == {
        owned.sender.id,
        owned.recipient.id,
    }
    assert {hint.resource_id for hint in by_kind["conversation.goal_shared"]} == {
        owned.conversation_id
    }
    blocked = {hint.recipient_id: hint for hint in by_kind["block.changed"]}
    assert blocked[owned.sender.id].resource_type == ChangeResource.ACCOUNT
    assert blocked[owned.sender.id].resource_id == owned.sender.id
    assert blocked[owned.recipient.id].resource_type == ChangeResource.CONVERSATION
    assert blocked[owned.recipient.id].resource_id == owned.conversation_id
    assert by_kind["operator.inspected"] == ()


async def test_actual_study_prompt_outcome_and_feedback_sources_keep_private_answers_scoped(
    identity_engine: AsyncEngine,
) -> None:
    from tests.integration.feedback.fixture import prepared
    from tests.integration.feedback.test_commands import make_old_acceptance

    api = await prepared(identity_engine)
    await api.exchange()
    await make_old_acceptance(api)
    receipt = await api.prompts()(api.visit())
    assert receipt is not None
    await api.outcomes()(api.outcome())
    await api.feedback()(api.review())
    async with api.chat.api.sessions() as session:
        events = tuple(await session.scalars(select(ProductEventRecord)))
        projected = await project_change_hints(session, events)
    by_kind = {event.kind: projected[event.id] for event in events}
    for kind in ("study.reported", "study.prompt_offered"):
        assert len(by_kind[kind]) == 1
        assert by_kind[kind][0].recipient_id == api.chat.sender.id
        assert by_kind[kind][0].resource_type == ChangeResource.CONVERSATION
        assert by_kind[kind][0].resource_id == api.chat.conversation_id
    feedback = by_kind["feedback.saved"]
    assert {hint.recipient_id for hint in feedback} == {api.chat.sender.id, api.chat.recipient.id}
    assert all(hint.resource_type == ChangeResource.ACCOUNT for hint in feedback)
    assert all(hint.resource_id == hint.recipient_id for hint in feedback)
    assert "Synthetic private team note" not in repr(projected)


async def test_projection_rejects_forged_canonical_actor_and_missing_source_without_private_hints(
    identity_engine: AsyncEngine,
) -> None:
    from studymate.application.discovery.profiles import ReadDiscoveryProfile
    from studymate.application.requests.queries import ReadRequest
    from studymate.application.requests.viewing import AcknowledgeRequestViewed, ViewRequestCommand
    from studymate.application.safety.blocks import ChangeBlockCommand, ChangeOwnBlock
    from studymate.infrastructure.feedback.transactions import SqlFeedbackUnitOfWork
    from studymate.infrastructure.persistence.blocks import SqlBlockUnitOfWork
    from studymate.infrastructure.persistence.discovery_profiles import (
        SqlDiscoveryProfileUnitOfWork,
    )
    from studymate.infrastructure.persistence.product_events import record_request_viewed
    from studymate.infrastructure.requests.queries import SqlRequestQueryUnitOfWork
    from studymate.infrastructure.requests.viewing import SqlRequestViewUnitOfWork
    from tests.integration.feedback.fixture import RECORDERS, FeedbackServices
    from tests.integration.messaging.goal_share_fixture import command, sharing

    owned = await chat(identity_engine)
    await owned.send()(owned.command())
    await owned.send()(owned.command(owned.recipient))
    await sharing(owned).share(await command(owned))
    async with owned.api.sessions() as session:
        request_id = (
            await session.scalars(
                select(ProductEventRecord.connection_request_id).where(
                    ProductEventRecord.kind == "request.changed"
                )
            )
        ).first()
    assert request_id is not None
    detail = await ReadRequest(SqlRequestQueryUnitOfWork(owned.api.sessions), HASHER)(
        owned.recipient.credential, request_id
    )
    await AcknowledgeRequestViewed(
        SqlRequestViewUnitOfWork(owned.api.sessions, record_request_viewed), HASHER, FINGERPRINTER
    )(
        ViewRequestCommand(
            owned.recipient.credential, request_id, detail.disclosure.id, IntentKey(str(uuid4()))
        )
    )
    api = FeedbackServices(owned, SqlFeedbackUnitOfWork(owned.api.sessions, RECORDERS))
    await api.outcomes()(api.outcome())
    await api.feedback()(api.review())
    profile = await ReadDiscoveryProfile(SqlDiscoveryProfileUnitOfWork(owned.api.sessions), HASHER)(
        owned.sender.credential, owned.recipient.id
    )
    await ChangeOwnBlock(SqlBlockUnitOfWork(owned.api.sessions), HASHER, FINGERPRINTER)(
        ChangeBlockCommand(
            owned.sender.credential,
            owned.recipient.id,
            True,
            0,
            IntentKey(str(uuid4())),
            profile.access_context.id,
        )
    )
    async with owned.api.sessions() as session:
        events = tuple(await session.scalars(select(ProductEventRecord)))
        correct = await project_change_hints(session, events)
    # Detached metadata is deliberately corrupted; immutable persisted sources remain genuine.
    kinds = {
        "request.changed",
        "message.confirmed",
        "request.view_acknowledged",
        "conversation.goal_shared",
        "block.changed",
        "feedback.saved",
    }
    for event in events:
        if event.kind not in kinds:
            continue
        original = event.account_id
        event.account_id = uuid4()
        try:
            async with owned.api.sessions() as session:
                with pytest.raises(RuntimeError, match=r"actual canonical|actual accepted"):
                    await project_change_hints(session, (event,))
        finally:
            event.account_id = original
    async with owned.api.sessions() as session:
        assert await project_change_hints(session, events) == correct


async def test_missing_source_and_duplicate_batches_fail_before_any_hints_are_returned(
    identity_engine: AsyncEngine,
) -> None:
    from tests.integration.change_fixture import message_events

    owned = await chat(identity_engine)
    await owned.send()(owned.command())
    events = await message_events(owned)
    async with owned.api.sessions() as session:
        correct = await project_change_hints(session, events)
    message_event = next(event for event in events if event.kind == "message.confirmed")
    original_operation = message_event.message_operation_id
    message_event.message_operation_id = None
    try:
        async with owned.api.sessions() as session:
            with pytest.raises(RuntimeError, match="required immutable source"):
                await project_change_hints(session, (message_event,))
    finally:
        message_event.message_operation_id = original_operation
    async with owned.api.sessions() as session:
        with pytest.raises(ValueError, match="distinct bounded"):
            await project_change_hints(session, (message_event, message_event))
        assert await project_change_hints(session, events) == correct
