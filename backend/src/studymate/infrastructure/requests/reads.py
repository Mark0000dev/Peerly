from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.application.requests.ports import (
    AcceptedRequest,
    AlreadyConnected,
    ExistingOutgoing,
    IncomingRequestExists,
    RequestPreview,
    RequestResult,
    SentRequest,
)
from studymate.domain.relationships import AccountPair
from studymate.domain.requests.states import ConnectionRequest
from studymate.infrastructure.persistence.conversation_models import ConversationRecord
from studymate.infrastructure.persistence.conversations import conversation_reference
from studymate.infrastructure.requests.codec import StoredRequestSnapshotError
from studymate.infrastructure.requests.models import (
    ConnectionRequestRecord,
    RequestCommandIntentRecord,
    RequestPreviewRecord,
    RequestRevisionRecord,
)
from studymate.infrastructure.requests.values import preview_value, request_value


async def read_preview(session: AsyncSession, preview_id: UUID) -> RequestPreview | None:
    record = await session.get(RequestPreviewRecord, preview_id)
    return preview_value(record) if record is not None else None


async def read_request(
    session: AsyncSession, request_id: UUID, version: int | None = None
) -> ConnectionRequest | None:
    statement = (
        select(ConnectionRequestRecord, RequestRevisionRecord, RequestPreviewRecord)
        .join(
            RequestRevisionRecord,
            (RequestRevisionRecord.request_id == ConnectionRequestRecord.id)
            & (
                RequestRevisionRecord.version
                == (ConnectionRequestRecord.current_version if version is None else version)
            ),
        )
        .join(RequestPreviewRecord, RequestPreviewRecord.id == ConnectionRequestRecord.preview_id)
        .where(ConnectionRequestRecord.id == request_id)
    )
    row = (await session.execute(statement)).one_or_none()
    return request_value(*row) if row is not None else None


async def intent_result(session: AsyncSession, record: RequestCommandIntentRecord) -> RequestResult:
    if record.result_kind == "preview" and record.result_preview_id is not None:
        preview = await read_preview(session, record.result_preview_id)
        if (
            preview is None
            or preview.context.sender_id != record.actor_id
            or preview.context.recipient_id != record.peer_id
        ):
            raise StoredRequestSnapshotError("Stored preview outcome has wrong owner")
        return preview
    if record.result_request_id is None or record.result_request_version is None:
        raise StoredRequestSnapshotError("Stored request outcome lacks a revision")
    request = await read_request(session, record.result_request_id, record.result_request_version)
    if request is None or request.pair != AccountPair.between(record.actor_id, record.peer_id):
        raise StoredRequestSnapshotError("Stored request outcome has wrong pair")
    if record.result_kind == "sent":
        return SentRequest(request)
    if record.result_kind == "outgoing":
        return ExistingOutgoing(request)
    if record.result_kind == "incoming":
        return IncomingRequestExists(request)
    if record.result_kind == "request":
        return request
    if record.result_kind not in {"connected", "accepted"} or record.result_conversation_id is None:
        raise StoredRequestSnapshotError("Stored outcome has invalid result kind")
    conversation = await session.get(ConversationRecord, record.result_conversation_id)
    if (
        conversation is None
        or conversation.request_id != request.id
        or conversation.accepted_request_version != request.version
    ):
        raise StoredRequestSnapshotError("Stored conversation outcome has invalid source")
    reference = conversation_reference(conversation)
    return (
        AlreadyConnected(reference)
        if record.result_kind == "connected"
        else AcceptedRequest(request, reference)
    )
