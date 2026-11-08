from studymate.application.requests.ports import RequestPreview
from studymate.domain.requests.context import RequestText
from studymate.domain.requests.states import ConnectionRequest, RequestState
from studymate.infrastructure.requests.codec import (
    StoredRequestSnapshotError,
    decode_context,
    encode_context,
)
from studymate.infrastructure.requests.models import (
    ConnectionRequestRecord,
    RequestPreviewRecord,
    RequestRevisionRecord,
)


def preview_value(record: RequestPreviewRecord) -> RequestPreview:
    value = decode_context(record.source_json)
    references = (
        value.sender_id,
        value.recipient_id,
        value.mode.value,
        value.subject_id,
        value.sender_goal.goal.id if value.sender_goal is not None else None,
        value.sender_goal.goal.version if value.sender_goal is not None else None,
        value.recipient_goal.goal.id if value.recipient_goal is not None else None,
        value.recipient_goal.goal.version if value.recipient_goal is not None else None,
        value.sender_help.revision.version if value.sender_help is not None else None,
        value.recipient_help.revision.version if value.recipient_help is not None else None,
    )
    stored = (
        record.sender_id,
        record.recipient_id,
        record.mode,
        record.subject_id,
        record.sender_goal_id,
        record.sender_goal_version,
        record.recipient_goal_id,
        record.recipient_goal_version,
        record.sender_help_version,
        record.recipient_help_version,
    )
    if stored != references:
        raise StoredRequestSnapshotError("Stored request sources disagree with owned references")
    return RequestPreview(record.id, value, record.created_at)


def preview_record(value: RequestPreview) -> RequestPreviewRecord:
    source = value.context
    return RequestPreviewRecord(
        id=value.id,
        sender_id=source.sender_id,
        recipient_id=source.recipient_id,
        mode=source.mode.value,
        subject_id=source.subject_id,
        created_at=value.created_at,
        source_json=encode_context(source),
        sender_goal_id=source.sender_goal.goal.id if source.sender_goal is not None else None,
        sender_goal_version=source.sender_goal.goal.version
        if source.sender_goal is not None
        else None,
        recipient_goal_id=source.recipient_goal.goal.id
        if source.recipient_goal is not None
        else None,
        recipient_goal_version=source.recipient_goal.goal.version
        if source.recipient_goal is not None
        else None,
        sender_help_version=source.sender_help.revision.version
        if source.sender_help is not None
        else None,
        recipient_help_version=source.recipient_help.revision.version
        if source.recipient_help is not None
        else None,
    )


def request_value(
    record: ConnectionRequestRecord, revision: RequestRevisionRecord, preview: RequestPreviewRecord
) -> ConnectionRequest:
    context = preview_value(preview).context
    if (context.sender_id, context.recipient_id) != (record.sender_id, record.recipient_id):
        raise StoredRequestSnapshotError("Stored request belongs to another preview")
    value = ConnectionRequest(
        record.id,
        record.relationship_id,
        record.preview_id,
        context,
        RequestText(record.request_text, record.note),
        record.sent_at,
        revision.changed_at,
        revision.version,
        RequestState(revision.state),
        revision.decline_until,
        revision.conversation_id,
    )
    if value.expires_at != record.expires_at or (value.pair.low, value.pair.high) != (
        record.low_id,
        record.high_id,
    ):
        raise StoredRequestSnapshotError("Stored request deadline or pair does not conform")
    return value


def revision_record(value: ConnectionRequest) -> RequestRevisionRecord:
    return RequestRevisionRecord(
        request_id=value.id,
        version=value.version,
        state=value.state.value,
        changed_at=value.changed_at,
        decline_until=value.decline_until,
        conversation_id=value.conversation_id,
    )
