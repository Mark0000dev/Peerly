"""Retained accepted graph for operator text reads, never student-send acceptance."""

from collections.abc import Mapping
from datetime import timedelta
from uuid import UUID

from operator_retained_fixture import SOURCE_TIME, retained_id
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.requests.context import GoalSnapshot, HelpSnapshot, RequestContext
from studymate.domain.study_context import (
    CanonicalSubjectRef,
    GoalContent,
    HelpRevision,
    HelpSubject,
    HelpSubjects,
    StudyGoal,
)
from studymate.infrastructure.persistence.block_models import RelationshipRecord
from studymate.infrastructure.persistence.conversation_models import ConversationRecord
from studymate.infrastructure.persistence.goal_models import (
    GoalRecord,
    GoalRevisionRecord,
)
from studymate.infrastructure.persistence.message_models import (
    MessageOperationRecord,
    MessageRecord,
)
from studymate.infrastructure.requests.codec import encode_context
from studymate.infrastructure.requests.models import (
    ConnectionRequestRecord,
    RequestPreviewRecord,
    RequestRevisionRecord,
)

MESSAGE_COUNT = 53


async def seed_conversation_records(
    engine: AsyncEngine, namespace: str, targets: Mapping[str, str]
) -> dict[str, str]:
    sender, recipient = UUID(targets["hidden_id"]), UUID(targets["deleted_id"])
    low, high = sorted((sender, recipient))
    goal, preview, request, pair, conversation = (
        retained_id(namespace, label)
        for label in ("source-goal", "preview", "request", "pair", "conversation")
    )
    at = SOURCE_TIME + timedelta(days=3, minutes=1)
    content = GoalContent(CanonicalSubjectRef(UUID(int=31)), topic="JOINs")
    context = RequestContext(
        sender,
        recipient,
        DiscoveryMode.FIND_HELP,
        sender_goal=GoalSnapshot(StudyGoal(goal, sender, 1, content, at, at), "SQL"),
        recipient_help=HelpSnapshot(
            HelpRevision(recipient, 1, HelpSubjects((HelpSubject(UUID(int=31)),)), at),
            ("SQL",),
        ),
    )
    count = 0 if namespace.split("/")[1] == "conversations-empty" else MESSAGE_COUNT
    async with async_sessionmaker(engine).begin() as session:
        session.add(
            GoalRecord(
                id=goal,
                account_id=sender,
                current_version=1,
                created_at=at,
                completed_at=None,
            )
        )
        await session.flush()
        session.add(
            GoalRevisionRecord(
                goal_id=goal,
                account_id=sender,
                version=1,
                subject_id=UUID(int=31),
                subject_label="SQL",
                topic="JOINs",
                topic_match_key="joins",
                context=None,
                shared_learning=False,
                saved_at=at,
                completed_at=None,
            )
        )
        session.add(RelationshipRecord(id=pair, low_id=low, high_id=high))
        await session.flush()
        session.add(
            RequestPreviewRecord(
                id=preview,
                sender_id=sender,
                recipient_id=recipient,
                mode="find_help",
                subject_id=UUID(int=31),
                created_at=at,
                source_json=encode_context(context),
                sender_goal_id=goal,
                sender_goal_version=1,
                recipient_goal_id=None,
                recipient_goal_version=None,
                sender_help_version=None,
                recipient_help_version=1,
            )
        )
        await session.flush()
        session.add(
            ConnectionRequestRecord(
                id=request,
                relationship_id=pair,
                low_id=low,
                high_id=high,
                sender_id=sender,
                recipient_id=recipient,
                preview_id=preview,
                request_text="Retained SQL practice request",
                note=None,
                sent_at=at,
                expires_at=at + timedelta(days=7),
                current_version=2,
                state="accepted",
                decision_sequence=1,
                request_id=None,
                action_id=None,
                trace_id=None,
                span_id=None,
            )
        )
        await session.flush()
        session.add(
            ConversationRecord(
                id=conversation,
                relationship_id=pair,
                low_id=low,
                high_id=high,
                request_id=request,
                accepted_request_version=2,
                request_state="accepted",
                next_message_sequence=count + 1,
            )
        )
        session.add_all(
            (
                RequestRevisionRecord(
                    request_id=request,
                    version=1,
                    state="pending",
                    changed_at=at,
                    decline_until=None,
                    conversation_id=None,
                ),
                RequestRevisionRecord(
                    request_id=request,
                    version=2,
                    state="accepted",
                    changed_at=at + timedelta(seconds=1),
                    decline_until=None,
                    conversation_id=conversation,
                ),
            )
        )
        await session.flush()
        for sequence in range(1, count + 1):
            author = sender if sequence % 2 else recipient
            operation, message, client = (
                retained_id(namespace, f"{kind}/{sequence}")
                for kind in ("operation", "message", "client-message")
            )
            session.add(
                MessageOperationRecord(
                    id=operation,
                    conversation_id=conversation,
                    low_id=low,
                    high_id=high,
                    author_id=author,
                    client_message_id=client,
                    state="confirmed",
                    message_id=message,
                    cancelled_at=None,
                )
            )
            await session.flush()
            session.add(
                MessageRecord(
                    id=message,
                    operation_id=operation,
                    conversation_id=conversation,
                    low_id=low,
                    high_id=high,
                    author_id=author,
                    client_message_id=client,
                    state="confirmed",
                    sequence=sequence,
                    text=f"Stored message {sequence}: <b>literal SQL</b>\nOriginal spacing",
                    sent_at=at + timedelta(seconds=sequence + 1),
                )
            )
    return {
        "conversation_id": str(conversation),
        "conversation_request_id": str(request),
        "conversation_relationship_id": str(pair),
        "conversation_low_id": str(low),
        "conversation_high_id": str(high),
    }
