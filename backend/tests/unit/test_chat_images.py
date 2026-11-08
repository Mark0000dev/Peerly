from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from studymate.domain.chat_images import ChatImageFailure, ChatImagePreparation, ChatImageState
from studymate.domain.media import PhotoContentType, PhotoSource

NOW = datetime(2026, 11, 8, tzinfo=UTC)
FIRST_ATTEMPT = UUID(int=5)
SECOND_ATTEMPT = UUID(int=6)


def preparation() -> ChatImagePreparation:
    return ChatImagePreparation(
        UUID(int=1),
        UUID(int=2),
        UUID(int=3),
        UUID(int=4),
        PhotoSource(100, b"p" * 32, PhotoContentType.PNG),
        NOW,
        NOW + timedelta(minutes=15),
        NOW + timedelta(hours=1),
        NOW,
    )


def test_prepared_image_keeps_exact_conversation_message_source_and_attempt_binding() -> None:
    original = preparation()
    queued = original.queue(NOW)
    processing = queued.claim(FIRST_ATTEMPT, NOW)
    ready = processing.ready(FIRST_ATTEMPT, NOW)
    assert (original.version, queued.version, processing.version, ready.version) == (1, 2, 3, 4)
    assert original.state == ChatImageState.UPLOADING
    assert ready.state == ChatImageState.READY
    for revision in (queued, processing, ready):
        assert revision.id == original.id
        assert revision.account_id == original.account_id
        assert revision.conversation_id == original.conversation_id
        assert revision.client_message_id == original.client_message_id
        assert revision.source == original.source
    assert ready.attempt_id == FIRST_ATTEMPT
    assert not ready.pending
    assert "pppp" not in repr(ready)


def test_old_processing_attempt_cannot_publish_after_reclaim_or_retry() -> None:
    first = preparation().queue(NOW).claim(FIRST_ATTEMPT, NOW)
    second = first.claim(SECOND_ATTEMPT, NOW)
    with pytest.raises(ValueError, match="actual current"):
        second.ready(FIRST_ATTEMPT, NOW)
    assert second.ready(SECOND_ATTEMPT, NOW).state == ChatImageState.READY
    retry = first.retry(NOW)
    assert retry.state == ChatImageState.QUEUED
    with pytest.raises(ValueError, match="actual current"):
        retry.ready(FIRST_ATTEMPT, NOW)


@pytest.mark.parametrize(
    "terminal",
    [
        ChatImageState.READY,
        ChatImageState.REJECTED,
        ChatImageState.CANCELLED,
        ChatImageState.EXPIRED,
    ],
)
def test_terminal_preparation_cannot_be_restarted_or_overwritten(terminal: ChatImageState) -> None:
    processing = preparation().queue(NOW).claim(FIRST_ATTEMPT, NOW)
    revision = replace(
        processing,
        state=terminal,
        failure=ChatImageFailure.CONTENT_CHANGED if terminal == ChatImageState.REJECTED else None,
    )
    assert revision.cancel(NOW) is revision
    assert revision.queue(NOW) is revision
    assert revision.expire(NOW + timedelta(days=1)) is revision
    assert revision.reject(ChatImageFailure.STORAGE_UNAVAILABLE, NOW) is revision
    with pytest.raises(ValueError, match="queued or reclaimed"):
        revision.claim(SECOND_ATTEMPT, NOW)
    with pytest.raises(ValueError, match="processing image"):
        revision.retry(NOW)


@pytest.mark.parametrize("action", ["queue", "cancel", "reject"])
def test_upload_deadline_wins_at_exact_boundary(action: str) -> None:
    original = preparation()
    at = original.upload_expires_at
    expired = (
        original.queue(at)
        if action == "queue"
        else original.cancel(at)
        if action == "cancel"
        else original.reject(ChatImageFailure.CONTENT_CHANGED, at)
    )
    assert expired.state == ChatImageState.EXPIRED
    assert expired.failure is None
    assert expired.version == original.version + 1


@pytest.mark.parametrize("action", ["claim", "ready", "retry", "cancel", "reject"])
def test_processing_deadline_prevents_late_publication_or_retry(action: str) -> None:
    current = preparation().queue(NOW).claim(FIRST_ATTEMPT, NOW)
    at = current.processing_expires_at
    expired = (
        current.claim(SECOND_ATTEMPT, at)
        if action == "claim"
        else current.ready(FIRST_ATTEMPT, at)
        if action == "ready"
        else current.retry(at)
        if action == "retry"
        else current.cancel(at)
        if action == "cancel"
        else current.reject(ChatImageFailure.INVALID_IMAGE, at)
    )
    assert expired.state == ChatImageState.EXPIRED
    assert expired.attempt_id == FIRST_ATTEMPT
    assert expired.failure is None


def test_queued_upload_can_process_after_upload_deadline_but_before_processing_deadline() -> None:
    queued = preparation().queue(NOW)
    later = queued.upload_expires_at + timedelta(seconds=1)
    assert queued.expire(later) is queued
    assert (
        queued.claim(FIRST_ATTEMPT, later).ready(FIRST_ATTEMPT, later).state == ChatImageState.READY
    )


def test_cancellation_fences_a_late_worker_without_erasing_source_or_attempt() -> None:
    processing = preparation().queue(NOW).claim(FIRST_ATTEMPT, NOW)
    cancelled = processing.cancel(NOW)
    assert cancelled.state == ChatImageState.CANCELLED
    assert cancelled.attempt_id == FIRST_ATTEMPT
    assert cancelled.source is processing.source
    with pytest.raises(ValueError, match="actual current"):
        cancelled.ready(FIRST_ATTEMPT, NOW)


@pytest.mark.parametrize("version", [True, 0, -1])
def test_invalid_history_versions_are_rejected(version: int) -> None:
    with pytest.raises(ValueError, match="revision must be positive"):
        replace(preparation(), version=version)


def test_revision_cannot_move_backwards_or_invent_rejection_and_ready_metadata() -> None:
    current = preparation().queue(NOW + timedelta(seconds=1))
    with pytest.raises(ValueError, match="precede its current"):
        current.cancel(NOW)
    with pytest.raises(ValueError, match="requires its failure"):
        replace(current, state=ChatImageState.REJECTED)
    with pytest.raises(ValueError, match="actual attempt"):
        replace(current, state=ChatImageState.READY)
    with pytest.raises(ValueError, match="deadlines must follow"):
        replace(current, upload_expires_at=NOW)
    with pytest.raises(ValueError, match="cannot precede creation"):
        replace(current, updated_at=NOW - timedelta(seconds=1))
    with pytest.raises(ValueError, match="timezone"):
        replace(current, updated_at=NOW.replace(tzinfo=None))


def test_content_failure_is_a_retained_terminal_fact_not_a_retriable_publication() -> None:
    queued = preparation().queue(NOW)
    rejected = queued.reject(ChatImageFailure.CONTENT_CHANGED, NOW)
    assert rejected.state == ChatImageState.REJECTED
    assert rejected.failure == ChatImageFailure.CONTENT_CHANGED
    assert queued.failure is None
    assert queued.state == ChatImageState.QUEUED
    assert rejected.source is queued.source
    assert rejected.reject(ChatImageFailure.STORAGE_UNAVAILABLE, NOW) is rejected
    with pytest.raises(ValueError, match="requires its failure"):
        replace(queued, failure=ChatImageFailure.STORAGE_UNAVAILABLE)
