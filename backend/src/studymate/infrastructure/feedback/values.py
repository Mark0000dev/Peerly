"""Typed immutable feedback sources reconstructed from retained actual records."""

from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.domain.feedback.assessments import (
    FeedbackContent,
    FeedbackDescriptor,
    FeedbackRemoval,
    FeedbackRevision,
    RemovalKind,
    StudyAgain,
)
from studymate.domain.feedback.interaction import HumanMessageEvidence, InteractionEvidence
from studymate.domain.feedback.outcomes import StudyAnswer, StudyOutcomeRevision, StudyPromptReceipt
from studymate.domain.messaging import ChatConversation
from studymate.domain.relationships import AccountPair
from studymate.infrastructure.feedback.models import (
    PeerFeedbackRemovalRecord,
    PeerFeedbackRevisionRecord,
    StudyOutcomeRevisionRecord,
    StudyPromptReceiptRecord,
)
from studymate.infrastructure.observability.tracing import current_origin
from studymate.infrastructure.persistence.conversation_models import ConversationRecord
from studymate.infrastructure.persistence.message_models import MessageRecord
from studymate.infrastructure.requests.models import RequestRevisionRecord


class OriginRecord(Protocol):
    http_request_id: UUID | None
    action_id: UUID | None
    trace_id: str | None
    span_id: str | None


def assign_origin(record: OriginRecord) -> None:
    origin = current_origin()
    record.http_request_id = origin.request_id if origin is not None else None
    record.action_id = origin.action_id if origin is not None else None
    record.trace_id = origin.trace_id if origin is not None else None
    record.span_id = origin.span_id if origin is not None else None


def outcome_value(row: StudyOutcomeRevisionRecord) -> StudyOutcomeRevision:
    return StudyOutcomeRevision(
        row.id,
        row.conversation_id,
        AccountPair(row.low_id, row.high_id),
        row.actor_id,
        row.version,
        StudyAnswer(row.answer),
        row.changed_at,
    )


def prompt_value(row: StudyPromptReceiptRecord) -> StudyPromptReceipt:
    return StudyPromptReceipt(row.id, row.conversation_id, row.actor_id, row.offered_at)


def removal_value(row: PeerFeedbackRemovalRecord) -> FeedbackRemoval:
    return FeedbackRemoval(
        row.feedback_id,
        row.source_version,
        row.operator_id,
        RemovalKind(row.kind),
        row.reason,
        row.removed_at,
    )


def conversation_value(row: ConversationRecord) -> ChatConversation:
    return ChatConversation(
        row.id,
        row.relationship_id,
        AccountPair(row.low_id, row.high_id),
        row.request_id,
        row.accepted_request_version,
        row.next_message_sequence,
    )


async def human_source(
    session: AsyncSession, conversation_id: UUID, author_id: UUID, message_id: UUID | None = None
) -> HumanMessageEvidence | None:
    statement = select(
        MessageRecord.id,
        MessageRecord.conversation_id,
        MessageRecord.author_id,
        MessageRecord.sequence,
        MessageRecord.sent_at,
    ).where(
        MessageRecord.conversation_id == conversation_id,
        MessageRecord.author_id == author_id,
        MessageRecord.state == "confirmed",
    )
    if message_id is not None:
        statement = statement.where(MessageRecord.id == message_id)
    row = (await session.execute(statement.order_by(MessageRecord.sequence).limit(1))).one_or_none()
    if row is None:
        if message_id is not None:
            raise RuntimeError("Retained feedback lost its actual owned human-message reference")
        return None
    return HumanMessageEvidence(
        row.id, row.conversation_id, row.author_id, row.sequence, row.sent_at
    )


async def interaction_value(
    session: AsyncSession,
    conversation: ConversationRecord,
    low_message: HumanMessageEvidence | None,
    high_message: HumanMessageEvidence | None,
) -> InteractionEvidence:
    accepted = await session.get(
        RequestRevisionRecord, (conversation.request_id, conversation.accepted_request_version)
    )
    if (
        accepted is None
        or accepted.state != "accepted"
        or accepted.conversation_id != conversation.id
    ):
        raise RuntimeError("Feedback lost the actual retained accepted request source")
    return InteractionEvidence.from_conversation(
        conversation_value(conversation), accepted.changed_at, low_message, high_message
    )


async def feedback_value(
    session: AsyncSession, row: PeerFeedbackRevisionRecord
) -> FeedbackRevision:
    conversation = await session.get(ConversationRecord, row.conversation_id)
    worked = await session.get(StudyOutcomeRevisionRecord, row.worked_confirmation_id)
    if conversation is None or worked is None:
        raise RuntimeError("Feedback lost its retained conversation or worked-Yes source")
    low = (
        await human_source(session, row.conversation_id, row.low_id, row.low_message_id)
        if row.low_message_id is not None
        else None
    )
    high = (
        await human_source(session, row.conversation_id, row.high_id, row.high_message_id)
        if row.high_message_id is not None
        else None
    )
    return FeedbackRevision(
        row.feedback_id,
        row.version,
        row.reviewer_id,
        await interaction_value(session, conversation, low, high),
        outcome_value(worked),
        FeedbackContent(
            StudyAgain(row.again),
            tuple(FeedbackDescriptor(value) for value in row.descriptors),
            row.team_note,
        ),
        row.changed_at,
    )
