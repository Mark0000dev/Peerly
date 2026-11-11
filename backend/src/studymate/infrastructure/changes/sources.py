"""Derive safe owned invalidations from actual immutable canonical source references."""

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.domain.changes import ChangeHint, ChangeResource
from studymate.infrastructure.changes.academic import academic_hints
from studymate.infrastructure.changes.lifecycle import lifecycle_hints
from studymate.infrastructure.feedback.models import PeerFeedbackRecord
from studymate.infrastructure.persistence.conversation_models import ConversationRecord
from studymate.infrastructure.persistence.message_models import MessageOperationRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.requests.models import ConnectionRequestRecord
from studymate.infrastructure.requests.view_models import RequestViewAcknowledgementRecord

MAX_CHANGE_SOURCE_BATCH = 100
ACCOUNT_KINDS = frozenset(
    {
        "auth.email_confirmed",
        "goal.saved",
        "goal.completed",
        "profile.ready",
        "profile.hidden",
        "profile.restored",
        "discovery.exposure_confirmed",
        "report.created",
        "discovery.pass_changed",
    }
)


def required(value: UUID | None) -> UUID:
    if value is None:
        raise RuntimeError("Canonical change hint lost its required immutable source")
    return value


async def project_change_hints(
    session: AsyncSession, events: tuple[ProductEventRecord, ...]
) -> dict[UUID, tuple[ChangeHint, ...]]:
    if len(events) > MAX_CHANGE_SOURCE_BATCH or len({event.id for event in events}) != len(events):
        raise ValueError("Change source projection requires distinct bounded canonical events")
    requests = (
        {
            request_id: (sender, recipient)
            for request_id, sender, recipient in await session.execute(
                select(
                    ConnectionRequestRecord.id,
                    ConnectionRequestRecord.sender_id,
                    ConnectionRequestRecord.recipient_id,
                ).where(
                    ConnectionRequestRecord.id.in_(
                        tuple(
                            required(event.connection_request_id)
                            for event in events
                            if event.kind == "request.changed"
                        )
                    )
                )
            )
        }
        if any(event.kind == "request.changed" for event in events)
        else {}
    )
    operations = (
        {
            operation_id: (conversation_id, author_id, low_id, high_id)
            for operation_id, conversation_id, author_id, low_id, high_id in await session.execute(
                select(
                    MessageOperationRecord.id,
                    MessageOperationRecord.conversation_id,
                    MessageOperationRecord.author_id,
                    MessageOperationRecord.low_id,
                    MessageOperationRecord.high_id,
                ).where(
                    MessageOperationRecord.id.in_(
                        tuple(
                            required(event.message_operation_id)
                            for event in events
                            if event.kind in {"message.confirmed", "message.cancelled"}
                        )
                    )
                )
            )
        }
        if any(event.kind in {"message.confirmed", "message.cancelled"} for event in events)
        else {}
    )
    acknowledgements = (
        {
            ack_id: (request_id, viewer_id)
            for ack_id, request_id, viewer_id in await session.execute(
                select(
                    RequestViewAcknowledgementRecord.id,
                    RequestViewAcknowledgementRecord.request_id,
                    RequestViewAcknowledgementRecord.viewer_id,
                ).where(
                    RequestViewAcknowledgementRecord.id.in_(
                        tuple(
                            required(event.request_view_ack_id)
                            for event in events
                            if event.kind == "request.view_acknowledged"
                        )
                    )
                )
            )
        }
        if any(event.kind == "request.view_acknowledged" for event in events)
        else {}
    )
    conversation_ids = tuple(
        required(event.goal_share_conversation_id)
        for event in events
        if event.kind == "conversation.goal_shared"
    )
    relationship_ids = tuple(
        required(event.block_relationship_id) for event in events if event.kind == "block.changed"
    )
    conversation_rows = (
        tuple(
            await session.execute(
                select(
                    ConversationRecord.id,
                    ConversationRecord.relationship_id,
                    ConversationRecord.low_id,
                    ConversationRecord.high_id,
                ).where(
                    or_(
                        ConversationRecord.id.in_(conversation_ids),
                        ConversationRecord.relationship_id.in_(relationship_ids),
                    )
                )
            )
        )
        if conversation_ids or relationship_ids
        else ()
    )
    conversations = {identifier: (low, high) for identifier, _, low, high in conversation_rows}
    relationships = {
        relationship: (identifier, low, high)
        for identifier, relationship, low, high in conversation_rows
    }
    feedback = (
        {
            identifier: (reviewer, partner)
            for identifier, reviewer, partner in await session.execute(
                select(
                    PeerFeedbackRecord.id,
                    PeerFeedbackRecord.reviewer_id,
                    PeerFeedbackRecord.partner_id,
                ).where(
                    PeerFeedbackRecord.id.in_(
                        tuple(
                            required(event.peer_feedback_id)
                            for event in events
                            if event.kind == "feedback.saved"
                        )
                    )
                )
            )
        }
        if any(event.kind == "feedback.saved" for event in events)
        else {}
    )
    sources = _HintSources(
        requests, operations, acknowledgements, conversations, relationships, feedback
    )
    academic = await academic_hints(session, events)
    lifecycle = await lifecycle_hints(session, events)
    return {
        event.id: lifecycle[event.id]
        if event.id in lifecycle
        else academic[event.id]
        if event.id in academic
        else tuple(
            ChangeHint(event.id, recipient, kind, resource_id, version)
            for recipient, kind, resource_id, version in sources.resources(event)
        )
        for event in events
    }


type HintResource = tuple[UUID, ChangeResource, UUID, int | None]


@dataclass(frozen=True, slots=True)
class _HintSources:
    requests: Mapping[UUID, tuple[UUID, UUID]]
    operations: Mapping[UUID, tuple[UUID, UUID, UUID, UUID]]
    acknowledgements: Mapping[UUID, tuple[UUID, UUID]]
    conversations: Mapping[UUID, tuple[UUID, UUID]]
    relationships: Mapping[UUID, tuple[UUID, UUID, UUID]]
    feedback: Mapping[UUID, tuple[UUID, UUID]]

    def resources(self, event: ProductEventRecord) -> tuple[HintResource, ...]:
        result: tuple[HintResource, ...]
        if event.kind in ACCOUNT_KINDS:
            result = ((event.account_id, ChangeResource.ACCOUNT, event.account_id, None),)
        elif event.kind == "request.changed":
            result = self.request(event)
        elif event.kind in {"message.confirmed", "message.cancelled"}:
            result = self.message(event)
        elif event.kind == "request.view_acknowledged":
            result = self.view(event)
        elif event.kind == "conversation.read_acknowledged":
            result = (
                (
                    event.account_id,
                    ChangeResource.CONVERSATION,
                    required(event.read_conversation_id),
                    None,
                ),
            )
        elif event.kind == "conversation.goal_shared":
            result = self.share(event)
        elif event.kind == "block.changed":
            result = self.block(event)
        elif event.kind == "study.reported":
            result = (
                (
                    event.account_id,
                    ChangeResource.CONVERSATION,
                    required(event.study_conversation_id),
                    None,
                ),
            )
        elif event.kind == "study.prompt_offered":
            result = (
                (
                    event.account_id,
                    ChangeResource.CONVERSATION,
                    required(event.study_prompt_conversation_id),
                    None,
                ),
            )
        elif event.kind == "feedback.saved":
            result = self.assessment(event)
        elif event.kind == "ai_job.completed" and event.ai_kind != "triage_report":
            result = ((event.account_id, ChangeResource.AI_JOB, required(event.ai_job_id), None),)
        else:
            result = ()
        return result

    def request(self, event: ProductEventRecord) -> tuple[HintResource, ...]:
        request_id = required(event.connection_request_id)
        source = self.requests.get(request_id)
        if source is None or event.account_id != source[0]:
            raise RuntimeError("Request hint lost its actual canonical participants")
        return tuple(
            (recipient, ChangeResource.REQUEST, request_id, event.connection_request_version)
            for recipient in source
        )

    def message(self, event: ProductEventRecord) -> tuple[HintResource, ...]:
        operation = self.operations.get(required(event.message_operation_id))
        if operation is None or operation[1] != event.account_id:
            raise RuntimeError("Message hint lost its actual canonical author")
        conversation_id, author, low, high = operation
        recipients = (low, high) if event.kind == "message.confirmed" else (author,)
        return tuple(
            (recipient, ChangeResource.CONVERSATION, conversation_id, None)
            for recipient in recipients
        )

    def view(self, event: ProductEventRecord) -> tuple[HintResource, ...]:
        acknowledgement = self.acknowledgements.get(required(event.request_view_ack_id))
        if acknowledgement is None or acknowledgement[1] != event.account_id:
            raise RuntimeError("Request view hint lost its actual canonical viewer")
        return ((event.account_id, ChangeResource.REQUEST, acknowledgement[0], None),)

    def share(self, event: ProductEventRecord) -> tuple[HintResource, ...]:
        conversation_id = required(event.goal_share_conversation_id)
        participants = self.conversations.get(conversation_id)
        if participants is None or event.account_id not in participants:
            raise RuntimeError("Goal share hint lost its actual accepted participants")
        return tuple(
            (recipient, ChangeResource.CONVERSATION, conversation_id, None)
            for recipient in participants
        )

    def block(self, event: ProductEventRecord) -> tuple[HintResource, ...]:
        resources: tuple[HintResource, ...] = (
            (event.account_id, ChangeResource.ACCOUNT, event.account_id, None),
        )
        existing = self.relationships.get(required(event.block_relationship_id))
        if existing is not None:
            conversation_id, low, high = existing
            if event.account_id not in (low, high):
                raise RuntimeError("Block hint lost its actual canonical actor")
            peer = high if event.account_id == low else low
            resources += ((peer, ChangeResource.CONVERSATION, conversation_id, None),)
        return resources

    def assessment(self, event: ProductEventRecord) -> tuple[HintResource, ...]:
        participants = self.feedback.get(required(event.peer_feedback_id))
        if participants is None or participants[0] != event.account_id:
            raise RuntimeError("Feedback hint lost its actual canonical reviewer")
        return tuple(
            (recipient, ChangeResource.ACCOUNT, recipient, None) for recipient in participants
        )
