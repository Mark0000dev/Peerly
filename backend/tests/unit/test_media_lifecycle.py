from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from studymate.domain.media import (
    MAX_PHOTO_BYTES,
    PhotoContentType,
    PhotoFailure,
    PhotoRevision,
    PhotoSource,
    PhotoUpload,
    PhotoUploadState,
)

NOW = datetime(2026, 11, 7, tzinfo=UTC)


def upload() -> PhotoUpload:
    return PhotoUpload(
        uuid4(),
        uuid4(),
        PhotoSource(10, bytes(range(32)), PhotoContentType.PNG),
        0,
        NOW,
        NOW + timedelta(minutes=15),
        NOW + timedelta(hours=1),
        NOW,
    )


def test_photo_pipeline_preserves_input_and_only_current_attempt_can_finalize() -> None:
    original = upload()
    queued = original.queue(NOW)
    assert original.state == PhotoUploadState.UPLOADING
    assert queued.version == original.version + 1
    assert queued.queue(NOW) is queued
    first_attempt = uuid4()
    processing = queued.processing(first_attempt, NOW)
    reclaimed = processing.processing(uuid4(), NOW + timedelta(seconds=1))
    with pytest.raises(ValueError, match="current processing attempt"):
        reclaimed.ready(first_attempt, NOW + timedelta(seconds=2))
    assert reclaimed.attempt_id is not None
    ready = reclaimed.ready(reclaimed.attempt_id, NOW + timedelta(seconds=2))
    assert ready.state == PhotoUploadState.READY
    assert ready.source == original.source
    assert ready.cancel(NOW + timedelta(seconds=3)) is ready
    assert ready.queue(NOW + timedelta(seconds=3)) is ready
    assert ready.expire(original.processing_expires_at) is ready
    assert ready.reject(PhotoFailure.INVALID_IMAGE, NOW + timedelta(seconds=3)) is ready
    assert not ready.pending
    assert "sha256" not in repr(original)


@pytest.mark.parametrize("stage", ["uploading", "queued", "processing"])
def test_photo_cancel_wins_before_ready_and_late_attempt_cannot_publish(stage: str) -> None:
    value = upload()
    if stage != "uploading":
        value = value.queue(NOW)
    if stage == "processing":
        value = value.processing(uuid4(), NOW)
    cancelled = value.cancel(NOW)
    assert cancelled.state == PhotoUploadState.CANCELLED
    assert cancelled.cancel(NOW) is cancelled
    with pytest.raises(ValueError, match="current processing attempt"):
        cancelled.ready(value.attempt_id or uuid4(), NOW)
    with pytest.raises(ValueError, match="Only queued"):
        cancelled.processing(uuid4(), NOW)


def test_photo_deadlines_are_authoritative_for_queue_worker_cancel_and_rejection() -> None:
    value = upload()
    assert value.expire(NOW) is value
    assert value.queue(value.upload_expires_at).state == PhotoUploadState.EXPIRED
    assert value.cancel(value.upload_expires_at).state == PhotoUploadState.EXPIRED
    queued = value.queue(NOW)
    assert queued.queue(value.processing_expires_at).state == PhotoUploadState.EXPIRED
    assert queued.cancel(value.processing_expires_at).state == PhotoUploadState.EXPIRED
    assert queued.processing(uuid4(), value.processing_expires_at).state == PhotoUploadState.EXPIRED
    processing = queued.processing(uuid4(), NOW)
    assert processing.attempt_id is not None
    assert (
        processing.ready(processing.attempt_id, value.processing_expires_at).state
        == PhotoUploadState.EXPIRED
    )
    assert (
        processing.reject(PhotoFailure.CONTENT_CHANGED, value.processing_expires_at).state
        == PhotoUploadState.EXPIRED
    )


def test_photo_rejection_is_terminal_and_has_explicit_nonprivate_reason() -> None:
    rejected = upload().queue(NOW).reject(PhotoFailure.CONTENT_CHANGED, NOW)
    assert rejected.failure == PhotoFailure.CONTENT_CHANGED
    assert rejected.state == PhotoUploadState.REJECTED
    assert rejected.reject(PhotoFailure.INVALID_IMAGE, NOW) is rejected
    with pytest.raises(ValueError, match="explain its failure"):
        replace(rejected, failure=None)
    with pytest.raises(ValueError, match="explain its failure"):
        replace(upload(), failure=PhotoFailure.INVALID_IMAGE)


@pytest.mark.parametrize("size", [0, -1, True, MAX_PHOTO_BYTES + 1])
def test_photo_source_size_is_bounded(size: int) -> None:
    with pytest.raises(ValueError, match="size"):
        PhotoSource(size, bytes(range(32)), PhotoContentType.JPEG)


def test_photo_source_digest_and_revision_contracts() -> None:
    with pytest.raises(ValueError, match="SHA256"):
        PhotoSource(1, b"not a digest", PhotoContentType.PNG)
    value = upload()
    for version in (-1, True):
        with pytest.raises(ValueError, match="valid integers"):
            replace(value, expected_photo_version=version)
        with pytest.raises(ValueError, match="valid integers"):
            replace(value, version=version)
    with pytest.raises(ValueError, match="require an attempt"):
        replace(value, state=PhotoUploadState.READY)
    with pytest.raises(ValueError, match="positive"):
        PhotoRevision(uuid4(), 0, uuid4(), NOW)
    revision = PhotoRevision(uuid4(), 1, value.id, NOW)
    assert revision.upload_id == value.id


def test_photo_timestamps_must_be_aware_ordered_and_not_move_backwards() -> None:
    value = upload()
    with pytest.raises(ValueError, match="timezone"):
        replace(value, created_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="deadlines"):
        replace(value, upload_expires_at=NOW)
    with pytest.raises(ValueError, match="precede creation"):
        replace(value, updated_at=NOW - timedelta(seconds=1))
    with pytest.raises(ValueError, match="current revision"):
        value.queue(NOW - timedelta(seconds=1))


def test_photo_retry_is_explicit_and_obeys_processing_deadline() -> None:
    value = upload()
    with pytest.raises(ValueError, match="Only a processing"):
        value.retry(NOW)
    processing = value.queue(NOW).processing(uuid4(), NOW)
    retried = processing.retry(NOW)
    assert retried.state == PhotoUploadState.QUEUED
    assert retried.attempt_id == processing.attempt_id
    assert processing.retry(value.processing_expires_at).state == PhotoUploadState.EXPIRED
