"""Fresh database readiness, checked under the canonical execution-slot lock."""

from datetime import datetime, timedelta
from uuid import UUID

from studymate.application.ai.ports import AiUnavailableError
from studymate.domain.ai.jobs import Versions
from studymate.infrastructure.ai.models import AiSlotRecord

RUNTIME_HEARTBEAT_SECONDS = 5
RUNTIME_TTL = timedelta(seconds=15)


def require_runtime_ready(
    slot: AiSlotRecord,
    at: datetime,
    versions: Versions | None = None,
    *,
    worker_id: UUID | None = None,
) -> Versions:
    if (
        slot.runtime_state != "ready"
        or slot.runtime_worker_id is None
        or (worker_id is not None and slot.runtime_worker_id != worker_id)
        or slot.runtime_started_at is None
        or slot.runtime_heartbeat_at is None
        or slot.runtime_valid_until is None
        or not slot.runtime_started_at <= slot.runtime_heartbeat_at <= at < slot.runtime_valid_until
        or slot.runtime_valid_until != slot.runtime_heartbeat_at + RUNTIME_TTL
        or slot.runtime_model is None
        or slot.runtime_prompt is None
        or slot.runtime_schema is None
        or slot.runtime_adapter is None
        or slot.circuit is not None
        or (slot.paused_until is not None and slot.paused_until > at)
    ):
        raise AiUnavailableError
    actual = Versions(
        slot.runtime_model, slot.runtime_prompt, slot.runtime_schema, slot.runtime_adapter
    )
    if versions is not None and actual != versions:
        raise AiUnavailableError
    return actual
