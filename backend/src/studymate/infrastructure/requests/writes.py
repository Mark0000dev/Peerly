from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from studymate.application.idempotency import IntentKey
from studymate.application.requests.ports import (
    AcceptedRequest,
    AlreadyConnected,
    ExistingOutgoing,
    IncomingRequestExists,
    RequestIntent,
    RequestPreview,
    SentRequest,
)
from studymate.domain.requests.limits import send_day
from studymate.domain.requests.states import ConnectionRequest, RequestState
from studymate.infrastructure.observability.tracing import current_origin
from studymate.infrastructure.persistence.conversation_models import ConversationRecord
from studymate.infrastructure.persistence.discovery_decisions import advance_discovery_decision
from studymate.infrastructure.requests.codec import StoredRequestSnapshotError
from studymate.infrastructure.requests.events import RequestOutcomeRecorder
from studymate.infrastructure.requests.models import (
    ConnectionRequestRecord,
    RequestCommandIntentRecord,
    RequestPreviewRecord,
    RequestSendDayRecord,
)
from studymate.infrastructure.requests.reads import read_request
from studymate.infrastructure.requests.values import preview_value, revision_record


async def save_request(
    session: AsyncSession,
    value: ConnectionRequest,
    initiator_id: UUID | None,
    recorder: RequestOutcomeRecorder,
) -> None:
    existing = await session.get(ConnectionRequestRecord, value.id)
    if existing is None:
        await insert_request(session, value, initiator_id)
    else:
        prior = await read_request(session, value.id)
        if prior == value:
            return
        if (
            prior is None
            or prior.version + 1 != value.version
            or prior.context != value.context
            or prior.message != value.message
            or prior.sent_at != value.sent_at
            or prior.relationship_id != value.relationship_id
            or prior.preview_id != value.preview_id
        ):
            raise StoredRequestSnapshotError("Request update violates immutable source or revision")
        if not prior.pending:
            raise StoredRequestSnapshotError("Terminal request cannot change again")
        existing.current_version = value.version
        existing.state = value.state.value
    session.add(revision_record(value))
    await session.flush()
    system = value.state in {RequestState.DECLINED, RequestState.EXPIRED}
    await recorder(session, value, None if system else initiator_id)


async def insert_request(
    session: AsyncSession, value: ConnectionRequest, initiator_id: UUID | None
) -> None:
    if (
        initiator_id != value.context.sender_id
        or value.version != 1
        or value.state != RequestState.PENDING
    ):
        raise RuntimeError("New request requires authoritative sender and initial pending state")
    preview = await session.get(RequestPreviewRecord, value.preview_id)
    if preview is None or preview_value(preview).context != value.context:
        raise StoredRequestSnapshotError("New request lacks its exact reviewed preview")
    sequence = await advance_discovery_decision(session, value.context.sender_id)
    record = ConnectionRequestRecord(
        id=value.id,
        relationship_id=value.relationship_id,
        low_id=value.pair.low,
        high_id=value.pair.high,
        sender_id=value.context.sender_id,
        recipient_id=value.context.recipient_id,
        preview_id=value.preview_id,
        request_text=value.message.text,
        note=value.message.note,
        sent_at=value.sent_at,
        expires_at=value.expires_at,
        current_version=value.version,
        state=value.state.value,
        decision_sequence=sequence,
    )
    origin = current_origin()
    if origin is not None:
        record.request_id, record.action_id, record.trace_id, record.span_id = (
            origin.request_id,
            origin.action_id,
            origin.trace_id,
            origin.span_id,
        )
    session.add(record)
    day = send_day(value.sent_at)
    counter = await session.get(RequestSendDayRecord, (value.context.sender_id, day))
    if counter is None:
        session.add(
            RequestSendDayRecord(
                sender_id=value.context.sender_id, local_day=day, successful_count=1
            )
        )
    else:
        counter.successful_count += 1
    await session.flush()


@dataclass(frozen=True, slots=True)
class IntentWrite:
    actor_id: UUID
    peer_id: UUID
    operation: str
    key: IntentKey
    intent: RequestIntent
    at: datetime


async def write_intent(session: AsyncSession, write: IntentWrite) -> None:
    actor_id, peer_id, operation = write.actor_id, write.peer_id, write.operation
    key, intent, at = write.key, write.intent, write.at
    record = RequestCommandIntentRecord(
        actor_id=actor_id,
        peer_id=peer_id,
        operation=operation,
        key=key.value,
        fingerprint=intent.fingerprint,
        created_at=at,
        result_kind="request",
    )
    result = intent.result
    request: ConnectionRequest | None = None
    if isinstance(result, RequestPreview):
        record.result_kind = "preview"
        record.result_preview_id = result.id
    elif isinstance(result, (SentRequest, ExistingOutgoing, IncomingRequestExists)):
        request = result.request
        record.result_kind = (
            "sent"
            if isinstance(result, SentRequest)
            else "outgoing"
            if isinstance(result, ExistingOutgoing)
            else "incoming"
        )
    elif isinstance(result, AlreadyConnected):
        conversation = await session.get(ConversationRecord, result.conversation.id)
        if conversation is None:
            raise StoredRequestSnapshotError("Connected outcome lacks actual conversation")
        request = await read_request(
            session, conversation.request_id, conversation.accepted_request_version
        )
        record.result_kind = "connected"
        record.result_conversation_id = conversation.id
    elif isinstance(result, AcceptedRequest):
        request = result.request
        record.result_kind = "accepted"
        record.result_conversation_id = result.conversation.id
    else:
        request = result
    if request is not None:
        record.result_request_id = request.id
        record.result_request_version = request.version
        record.result_request_state = request.state.value
        record.result_sender_id = request.context.sender_id
        record.result_recipient_id = request.context.recipient_id
    origin = current_origin()
    if origin is not None:
        record.request_id, record.action_id, record.trace_id, record.span_id = (
            origin.request_id,
            origin.action_id,
            origin.trace_id,
            origin.span_id,
        )
    session.add(record)
    await session.flush()
