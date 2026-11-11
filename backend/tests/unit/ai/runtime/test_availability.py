from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from studymate.application.ai.ports import AiUnavailableError
from studymate.domain.ai.jobs import Versions
from studymate.infrastructure.ai.models import AiSlotRecord
from studymate.infrastructure.ai.runtime.availability import require_runtime_ready


def ready() -> tuple[AiSlotRecord, datetime, Versions]:
    at = datetime.now(UTC)
    versions = Versions("synthetic-model")
    slot = AiSlotRecord(
        id=1,
        generation=0,
        sequence=0,
        interactive_streak=0,
        runtime_state="ready",
        runtime_worker_id=uuid4(),
        runtime_started_at=at,
        runtime_heartbeat_at=at,
        runtime_valid_until=at + timedelta(seconds=15),
        runtime_model=versions.model,
        runtime_prompt=versions.prompt,
        runtime_schema=versions.schema,
        runtime_adapter=versions.adapter,
    )
    return slot, at, versions


@pytest.mark.parametrize("state", ["starting", "blocked", "stopped"])
def test_not_ready_states_are_not_an_admission_grant(state: str) -> None:
    slot, at, _ = ready()
    slot.runtime_state = state
    with pytest.raises(AiUnavailableError):
        require_runtime_ready(slot, at)


def test_freshness_exact_version_and_owner_fencing() -> None:
    slot, at, versions = ready()
    assert require_runtime_ready(slot, at) == versions
    with pytest.raises(AiUnavailableError):
        require_runtime_ready(slot, at + timedelta(seconds=15))
    with pytest.raises(AiUnavailableError):
        require_runtime_ready(slot, at, Versions("other-model"))
    with pytest.raises(AiUnavailableError):
        require_runtime_ready(slot, at, worker_id=uuid4())
    slot.circuit = "auth_unavailable"
    with pytest.raises(AiUnavailableError):
        require_runtime_ready(slot, at)
