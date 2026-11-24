"""Failure-boundary units only; no database acceptance claim."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.application.errors import StorageUnavailableError
from studymate.infrastructure.persistence.message_models import MessageOperationRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.student_notifications.sources import target
from studymate.infrastructure.student_notifications.transaction_diagnostics import (
    Operation,
    Progress,
    Stage,
)


@pytest.mark.parametrize(
    "stage", [Stage.MESSAGE_OPERATION, Stage.MESSAGE_CONVERSATION, Stage.REQUEST_AUTHORITY]
)
async def test_source_failure_records_exact_authority_read_without_swallowing(
    monkeypatch: pytest.MonkeyPatch, stage: Stage
) -> None:
    progress = Progress(Operation.MATERIALIZE)
    event = ProductEventRecord(
        kind="request.changed" if stage == Stage.REQUEST_AUTHORITY else "message.confirmed",
        message_operation_id=uuid4(),
        connection_request_id=uuid4(),
    )
    failure = StorageUnavailableError("PRIVATE_SOURCE_TEXT")
    async with AsyncSession() as session:
        if stage == Stage.REQUEST_AUTHORITY:
            monkeypatch.setattr(session, "execute", AsyncMock(side_effect=failure))
        elif stage == Stage.MESSAGE_OPERATION:
            monkeypatch.setattr(session, "get", AsyncMock(side_effect=failure))
        else:
            operation = MessageOperationRecord(
                state="confirmed", message_id=uuid4(), conversation_id=uuid4()
            )
            monkeypatch.setattr(session, "get", AsyncMock(side_effect=[operation, failure]))
        with pytest.raises(StorageUnavailableError) as caught:
            await target(session, event, datetime.now(UTC), progress=progress)
    assert caught.value is failure
    assert progress.stage == stage
