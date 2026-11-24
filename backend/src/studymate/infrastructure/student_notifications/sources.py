"""Read only real immutable source identifiers, never chat/request text."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.domain.student_notifications.delivery import Kind
from studymate.infrastructure.persistence.conversation_models import ConversationRecord
from studymate.infrastructure.persistence.message_models import MessageOperationRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.requests.models import ConnectionRequestRecord
from studymate.infrastructure.student_notifications.transaction_diagnostics import Progress, Stage


@dataclass(frozen=True, slots=True)
class Target:
    recipient: UUID
    actor: UUID
    relationship: UUID
    kind: Kind
    source_current: bool


async def target(
    session: AsyncSession,
    event: ProductEventRecord,
    now: datetime,
    *,
    progress: Progress | None = None,
) -> Target:
    if event.kind == "message.confirmed" and event.message_operation_id is not None:
        if progress is not None:
            progress.stage = Stage.MESSAGE_OPERATION
        operation = await session.get(MessageOperationRecord, event.message_operation_id)
        if operation is None or operation.state != "confirmed" or operation.message_id is None:
            raise RuntimeError("Confirmed message source missing")
        if progress is not None:
            progress.stage = Stage.MESSAGE_CONVERSATION
        conversation = await session.get(ConversationRecord, operation.conversation_id)
        if conversation is None or operation.author_id not in (
            conversation.low_id,
            conversation.high_id,
        ):
            raise RuntimeError("Message has no actual participant conversation")
        recipient = (
            conversation.high_id
            if operation.author_id == conversation.low_id
            else conversation.low_id
        )
        return Target(
            recipient, operation.author_id, conversation.relationship_id, Kind.MESSAGE, True
        )
    if event.kind == "request.changed" and event.connection_request_id is not None:
        # Project only authority metadata: request_text/note/source_json never read.
        if progress is not None:
            progress.stage = Stage.REQUEST_AUTHORITY
        row = (
            await session.execute(
                select(
                    ConnectionRequestRecord.sender_id,
                    ConnectionRequestRecord.recipient_id,
                    ConnectionRequestRecord.relationship_id,
                    ConnectionRequestRecord.state,
                    ConnectionRequestRecord.expires_at,
                ).where(ConnectionRequestRecord.id == event.connection_request_id)
            )
        ).one_or_none()
        if row is None:
            raise RuntimeError("Request event lost its retained source")
        if event.connection_request_state == "accepted":
            return Target(
                row.sender_id,
                row.recipient_id,
                row.relationship_id,
                Kind.ACCEPTED_CONNECTION,
                row.state == "accepted",
            )
        if event.connection_request_state == "pending" and event.connection_request_version == 1:
            return Target(
                row.recipient_id,
                row.sender_id,
                row.relationship_id,
                Kind.REQUEST,
                row.state == "pending" and row.expires_at > now,
            )
    raise ValueError("No supported student notification source")
