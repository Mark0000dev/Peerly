from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.application.requests.ports import ConversationReference
from studymate.domain.relationships import AccountPair
from studymate.domain.requests.states import (
    ConnectionRequest,
    RequestState,
    RequestUnavailableError,
)
from studymate.infrastructure.persistence.conversation_models import ConversationRecord


def conversation_reference(record: ConversationRecord) -> ConversationReference:
    return ConversationReference(
        record.id,
        record.relationship_id,
        AccountPair(record.low_id, record.high_id),
        record.request_id,
    )


async def create_request_conversation(
    session: AsyncSession, request: ConnectionRequest, at: datetime
) -> ConversationReference:
    """Both account/pair locks already held; caller commits acceptance in this session."""
    effective = request.effective(at)
    if effective.state != RequestState.PENDING:
        raise RequestUnavailableError
    existing = await session.scalar(
        select(ConversationRecord).where(
            ConversationRecord.relationship_id == request.relationship_id
        )
    )
    if existing is not None:
        reference = conversation_reference(existing)
        if reference.pair != request.pair or reference.request_id != request.id:
            raise RuntimeError("Existing conversation belongs to another accepted source")
        return reference
    conversation = ConversationRecord(
        id=uuid4(),
        relationship_id=request.relationship_id,
        low_id=request.pair.low,
        high_id=request.pair.high,
        request_id=request.id,
        accepted_request_version=request.version + 1,
        request_state=RequestState.ACCEPTED.value,
        next_message_sequence=1,
    )
    session.add(conversation)
    # The deferred FK requires the actual accepted revision before this tx commits.
    await session.flush()
    return conversation_reference(conversation)
