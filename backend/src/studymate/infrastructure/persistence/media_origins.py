from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.domain.media import PhotoUpload, PhotoUploadState
from studymate.infrastructure.observability.origin import ExecutionOrigin
from studymate.infrastructure.observability.tracing import current_origin
from studymate.infrastructure.persistence.media_origin_models import MediaOriginRecord


async def retain_media_origin(session: AsyncSession, upload: PhotoUpload) -> None:
    origin = current_origin()
    if origin is None or upload.state not in (PhotoUploadState.UPLOADING, PhotoUploadState.QUEUED):
        return
    phase = "created" if upload.state == PhotoUploadState.UPLOADING else "queued"
    # Only the genuine first HTTP transition owns this link. Worker retries have no
    # HTTP origin; saved-intent replays never reach this write boundary.
    session.add(
        MediaOriginRecord(
            upload_id=upload.id,
            phase=phase,
            request_id=origin.request_id,
            action_id=origin.action_id,
            trace_id=origin.trace_id,
            span_id=origin.span_id,
            recorded_at=upload.updated_at,
        )
    )
    await session.flush()


async def read_media_origin(session: AsyncSession, upload_id: UUID) -> ExecutionOrigin | None:
    record = (
        await session.scalars(
            select(MediaOriginRecord)
            .where(MediaOriginRecord.upload_id == upload_id)
            .order_by(MediaOriginRecord.phase.desc())
            .limit(1)
        )
    ).one_or_none()
    if record is None:
        return None
    return ExecutionOrigin(record.request_id, record.action_id, record.trace_id, record.span_id)
