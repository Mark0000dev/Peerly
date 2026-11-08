import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.messaging.goal_shares import (
    GOAL_SHARE_PAGE_SIZE,
    GoalShareContextConflictError,
)
from studymate.application.messaging.ports import (
    ConversationUnavailableError,
    MessageContactUnavailableError,
)
from studymate.application.profiles.goals import (
    CompleteGoalCommand,
    CompleteOwnGoal,
    GoalVersionConflictError,
    ReadOwnGoal,
    SaveGoalCommand,
    SaveOwnGoal,
)
from studymate.domain.goal_shares import GoalShare
from studymate.domain.study_context import CustomSubjectRef, GoalContent
from studymate.infrastructure.messaging.goal_share_models import (
    ConversationGoalShareHeadRecord,
    ConversationGoalShareIntentRecord,
    ConversationGoalShareRecord,
)
from studymate.infrastructure.persistence.conversation_models import ConversationRecord
from studymate.infrastructure.persistence.discovery_pass_models import DiscoveryDecisionHeadRecord
from studymate.infrastructure.persistence.goals import SqlGoalUnitOfWork
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.message_models import MessageRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_conversation_goal_share
from studymate.presentation.messaging.goal_shares import goal_share_page
from tests.integration.messaging.goal_share_fixture import command, sharing
from tests.integration.onboarding_fixture import ready_setup
from tests.integration.profile_lifecycle_fixture import command as visibility_command
from tests.integration.profile_lifecycle_fixture import complete_existing_setup
from tests.integration.profile_lifecycle_fixture import services as visibility_services
from tests.integration.requests.fixture import FINGERPRINTER, HASHER, action, additional_peer, sent
from tests.integration.student_actor import actor
from tests.integration.test_message_commands import chat

pytestmark = pytest.mark.integration


async def test_baseline_zero_read_creates_no_share_head_or_human_message(
    identity_engine: AsyncEngine,
) -> None:
    context = await chat(identity_engine)
    api = sharing(context)
    baseline = await api.history(context.sender.credential, context.conversation_id)
    assert baseline.current_context_version == 0
    assert baseline.latest is None
    assert baseline.history == ()
    assert baseline.baseline.sender_goal_can_complete
    async with context.api.sessions() as session:
        conversation = await session.get(ConversationRecord, context.conversation_id)
        assert conversation is not None
        assert baseline.baseline.baseline.request_id == conversation.request_id
        assert (
            baseline.baseline.baseline.accepted_request_version
            == conversation.accepted_request_version
        )
        assert conversation.next_message_sequence == 1
        assert (
            await session.scalar(select(func.count()).select_from(ConversationGoalShareHeadRecord))
            == 0
        )
        assert (
            await session.scalar(select(func.count()).select_from(ConversationGoalShareRecord)) == 0
        )
        assert await session.scalar(select(func.count()).select_from(MessageRecord)) == 0


async def test_custom_hidden_goal_is_explicitly_shared_with_actual_fk_and_one_canonical_event(
    identity_engine: AsyncEngine,
) -> None:
    context = await chat(identity_engine)
    uow = SqlGoalUnitOfWork(context.api.sessions)
    current = await ReadOwnGoal(uow, HASHER)(context.sender.credential)
    assert current is not None
    custom = await SaveOwnGoal(uow, HASHER, FINGERPRINTER)(
        SaveGoalCommand(
            context.sender.credential,
            GoalContent(
                CustomSubjectRef("Private custom subject"),
                "Exact private topic",
                "Exact private retained context",
                False,
            ),
            current.goal.id,
            current.goal.version,
            IntentKey(str(uuid4())),
        )
    )
    visibility, _ = visibility_services(identity_engine)
    await visibility(visibility_command(context.sender))
    await visibility(visibility_command(context.recipient))
    api = sharing(context)
    submission = await command(context)
    original = await api.share(submission)
    assert original.goal == custom.goal
    assert original.subject_label == custom.subject_label
    assert original.goal.content.canonical_subject_id is None
    assert await api.share(submission) == original
    noop = await api.share(replace(submission, intent_key=IntentKey(str(uuid4()))))
    assert noop == original
    async with context.api.sessions() as session:
        assert (
            await session.scalar(select(func.count()).select_from(ConversationGoalShareRecord)) == 1
        )
        events = tuple(
            await session.scalars(
                select(ProductEventRecord).where(
                    ProductEventRecord.kind == "conversation.goal_shared"
                )
            )
        )
        assert len(events) == 1
        assert events[0].account_id == context.sender.id
        assert events[0].goal_share_id == original.id
        assert events[0].goal_share_context_version == original.context_version
        assert await session.scalar(select(ConversationRecord.next_message_sequence)) == 1
        assert await session.scalar(select(func.count()).select_from(MessageRecord)) == 0


async def test_opposite_shares_cas_and_identical_same_owner_race_are_truthful(
    identity_engine: AsyncEngine,
) -> None:
    context = await chat(identity_engine)
    api = sharing(context)
    first, second = await command(context), await command(context, context.recipient)
    results = await asyncio.gather(api.share(first), api.share(second), return_exceptions=True)
    assert sum(isinstance(result, GoalShare) for result in results) == 1
    assert sum(isinstance(result, GoalShareContextConflictError) for result in results) == 1
    latest = next(result for result in results if isinstance(result, GoalShare))
    owner = context.sender if latest.owner_id == context.sender.id else context.recipient
    current = await command(context, owner, context_version=0)
    replay, duplicate = await asyncio.gather(
        api.share(current), api.share(replace(current, intent_key=IntentKey(str(uuid4()))))
    )
    assert replay == duplicate == latest
    async with context.api.sessions() as session:
        assert (
            await session.scalar(select(func.count()).select_from(ConversationGoalShareRecord)) == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProductEventRecord)
                .where(ProductEventRecord.kind == "conversation.goal_shared")
            )
            == 1
        )


async def test_reshare_preserves_exact_old_sources_after_edit_and_done(
    identity_engine: AsyncEngine,
) -> None:
    context = await chat(identity_engine)
    api = sharing(context)
    first_command = await command(context)
    first = await api.share(first_command)
    other = await api.share(await command(context, context.recipient, first.context_version))
    await SaveOwnGoal(SqlGoalUnitOfWork(context.api.sessions), HASHER, FINGERPRINTER)(
        SaveGoalCommand(
            context.recipient.credential,
            replace(other.goal.content, topic="Private partner edit NOT shared"),
            other.goal.id,
            other.goal.version,
            IntentKey(str(uuid4())),
        )
    )
    private_peer_edit = await api.history(context.sender.credential, context.conversation_id)
    assert "Private partner edit" not in goal_share_page(private_peer_edit).model_dump_json()
    assert private_peer_edit.history[-1].share == other
    again = await api.share(await command(context, context.sender, other.context_version))
    assert again.goal == first.goal
    assert again.id != first.id
    uow = SqlGoalUnitOfWork(context.api.sessions)
    edited = await SaveOwnGoal(uow, HASHER, FINGERPRINTER)(
        SaveGoalCommand(
            context.sender.credential,
            replace(first.goal.content, topic="Private newly edited topic NOT shared"),
            first.goal.id,
            first.goal.version,
            IntentKey(str(uuid4())),
        )
    )
    observed = await api.history(context.sender.credential, context.conversation_id)
    assert not any(row.can_complete for row in observed.history)
    assert "Private newly edited" not in goal_share_page(observed).model_dump_json()
    assert observed.history[0].share == first
    await CompleteOwnGoal(uow, HASHER, FINGERPRINTER)(
        CompleteGoalCommand(
            context.sender.credential, edited.goal.id, edited.goal.version, IntentKey(str(uuid4()))
        )
    )
    assert await api.share(first_command) == first
    observed = await api.history(context.sender.credential, context.conversation_id)
    assert observed.latest is not None
    assert observed.latest.share == again
    assert [row.share.context_version for row in observed.history] == list(
        range(1, again.context_version + 1)
    )
    assert all(row.share.goal.active for row in observed.history)
    assert not any(row.can_complete for row in observed.history)


@pytest.mark.parametrize("failure", ["exception", "cancel"])
async def test_canonical_failure_or_cancellation_rolls_back_head_source_intent_and_event(
    identity_engine: AsyncEngine, failure: str
) -> None:
    context = await chat(identity_engine)
    recorded = asyncio.Event()

    async def failing(session: AsyncSession, share: GoalShare) -> None:
        await record_conversation_goal_share(session, share)
        recorded.set()
        if failure == "exception":
            raise RuntimeError("Synthetic goal-share canonical failure")
        await asyncio.Future[None]()

    api = sharing(context, failing)
    submission = await command(context)
    if failure == "exception":
        with pytest.raises(RuntimeError, match="canonical failure"):
            await api.share(submission)
    else:
        task = asyncio.create_task(api.share(submission))
        await asyncio.wait_for(recorded.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    async with context.api.sessions() as session:
        for table in (
            ConversationGoalShareRecord,
            ConversationGoalShareHeadRecord,
            ConversationGoalShareIntentRecord,
        ):
            assert await session.scalar(select(func.count()).select_from(table)) == 0
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProductEventRecord)
                .where(ProductEventRecord.kind == "conversation.goal_shared")
            )
            == 0
        )
    committed = await sharing(context).share(submission)
    assert committed.context_version == 1


async def test_foreign_goal_or_conversation_and_cross_conversation_intent_cannot_be_repurposed(
    identity_engine: AsyncEngine,
) -> None:
    context = await chat(identity_engine)
    api = sharing(context)
    original = await command(context)
    peer_goal = await command(context, context.recipient)
    with pytest.raises(GoalVersionConflictError):
        await api.share(
            replace(
                original,
                goal_id=peer_goal.goal_id,
                expected_goal_version=peer_goal.expected_goal_version,
            )
        )
    other = await actor(identity_engine)
    await ready_setup(identity_engine, other.credential)
    await complete_existing_setup(identity_engine, other)
    for conversation_id in (context.conversation_id, uuid4()):
        with pytest.raises(ConversationUnavailableError):
            await api.history(other.credential, conversation_id)
    first = await api.share(original)
    subject_id = first.goal.content.canonical_subject_id
    assert subject_id is not None
    additional = await additional_peer(identity_engine, subject_id)
    request = await sent(context.api, context.sender, additional)
    accepted = await context.api.accept(action(additional, context.sender, request))
    with pytest.raises(IdempotencyConflictError):
        await api.share(replace(original, conversation_id=accepted.conversation.id))
    async with context.api.sessions() as session:
        assert (
            await session.scalar(select(func.count()).select_from(ConversationGoalShareRecord)) == 1
        )
        assert await session.get(ConversationGoalShareHeadRecord, accepted.conversation.id) is None


async def test_context_history_is_anchored_bounded_and_does_not_advance_message_or_deck_sequence(
    identity_engine: AsyncEngine,
) -> None:
    context = await chat(identity_engine)
    api = sharing(context)
    async with context.api.sessions() as session:
        before = tuple(
            (row.account_id, row.last_sequence)
            for row in await session.scalars(
                select(DiscoveryDecisionHeadRecord).order_by(DiscoveryDecisionHeadRecord.account_id)
            )
        )
    for version in range(GOAL_SHARE_PAGE_SIZE + 1):
        owner = context.sender if version % 2 == 0 else context.recipient
        await api.share(await command(context, owner, version))
    first = await api.history(context.sender.credential, context.conversation_id)
    assert len(first.history) == GOAL_SHARE_PAGE_SIZE
    assert first.next_cursor is not None
    added = await api.share(
        await command(context, context.recipient, first.current_context_version)
    )
    older = await api.history(context.sender.credential, context.conversation_id, first.next_cursor)
    assert [row.share.context_version for row in older.history] == [1]
    assert older.current_context_version == added.context_version
    assert older.anchor_version == first.anchor_version
    assert older.next_cursor is None
    async with context.api.sessions() as session:
        after = tuple(
            (row.account_id, row.last_sequence)
            for row in await session.scalars(
                select(DiscoveryDecisionHeadRecord).order_by(DiscoveryDecisionHeadRecord.account_id)
            )
        )
        assert after == before
        assert await session.scalar(select(ConversationRecord.next_message_sequence)) == 1
        assert await session.scalar(select(func.count()).select_from(MessageRecord)) == 0


async def test_database_rejects_foreign_goal_source_and_foreign_canonical_owner(
    identity_engine: AsyncEngine,
) -> None:
    context = await chat(identity_engine)
    api = sharing(context)
    first = await api.share(await command(context))
    peer = await command(context, context.recipient)
    async with context.api.sessions() as session:
        session.add(
            ConversationGoalShareRecord(
                id=uuid4(),
                conversation_id=first.conversation_id,
                low_id=first.pair.low,
                high_id=first.pair.high,
                owner_id=first.owner_id,
                goal_id=peer.goal_id,
                goal_version=peer.expected_goal_version,
                context_version=first.context_version + 1,
                shared_at=first.shared_at,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
    async with context.api.sessions() as session:
        session.add(
            ProductEventRecord(
                id=uuid4(),
                account_id=context.recipient.id,
                kind="conversation.goal_shared",
                occurrence_key=f"synthetic-wrong-owner:{uuid4()}",
                schema_version=1,
                occurred_at=first.shared_at,
                goal_share_id=first.id,
                goal_share_conversation_id=first.conversation_id,
                goal_share_context_version=first.context_version,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
    async with context.api.sessions() as session:
        assert (
            await session.scalar(select(func.count()).select_from(ConversationGoalShareRecord)) == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProductEventRecord)
                .where(ProductEventRecord.kind == "conversation.goal_shared")
            )
            == 1
        )


async def test_peer_soft_delete_retains_goal_history_and_original_commit_recovery(
    identity_engine: AsyncEngine,
) -> None:
    context = await chat(identity_engine)
    api = sharing(context)
    submission = await command(context)
    source = await api.share(submission)
    async with context.api.sessions.begin() as session:
        at = await SqlIdentityTransaction(session).now()
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == context.recipient.id)
            .values(deleted_at=at)
        )
    assert await api.share(submission) == source
    with pytest.raises(MessageContactUnavailableError):
        await api.share(replace(submission, intent_key=IntentKey(str(uuid4()))))
    retained = await api.history(context.sender.credential, context.conversation_id)
    assert retained.latest is not None
    assert retained.latest.share == source
    assert retained.history[0].share.goal == source.goal
    assert retained.history[0].share.subject_label == source.subject_label
