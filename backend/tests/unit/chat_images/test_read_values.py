"""Fail closed on missing or unrelated READY metadata even before serialization."""

from uuid import uuid4

import pytest

from studymate.domain.chat_images import ChatImageState
from studymate.infrastructure.chat_images.models import (
    ChatImageAttemptRecord,
    ChatImageRecord,
    ChatImageRevisionRecord,
)
from studymate.infrastructure.chat_images.reads import source_value
from tests.unit.chat_images.test_reads import ReadStore, image
from tests.unit.identity_store import NOW


@pytest.mark.parametrize("fault", ["missing", "other", "outcome", "metadata"])
def test_ready_projection_requires_actual_owned_successful_attempt(fault: str) -> None:
    original = image(ReadStore())
    attempt_id = uuid4()
    root = ChatImageRecord(
        id=original.id,
        account_id=original.account_id,
        conversation_id=original.conversation_id,
        client_message_id=original.client_message_id,
        source_size=original.source.size,
        source_digest=original.source.sha256,
        content_type=original.source.content_type.value,
        created_at=original.created_at,
        upload_expires_at=original.upload_expires_at,
        processing_expires_at=original.processing_expires_at,
    )
    revision = ChatImageRevisionRecord(
        image_id=original.id,
        version=1,
        state=ChatImageState.READY.value,
        attempt_id=attempt_id,
        updated_at=NOW,
    )
    attempt = (
        None
        if fault == "missing"
        else ChatImageAttemptRecord(
            id=attempt_id,
            image_id=uuid4() if fault == "other" else original.id,
            outcome="processing" if fault == "outcome" else "ready",
            display_width=None if fault == "metadata" else 10,
            display_height=10,
            display_size=100,
        )
    )
    with pytest.raises(RuntimeError, match="actual owned ready"):
        source_value(root, revision, attempt, None)
