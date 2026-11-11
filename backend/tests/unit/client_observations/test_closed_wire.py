"""Privacy/bounds regression definitions; no generic client telemetry bags."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from studymate.domain.client_observations.events import MAX_EVENTS
from studymate.presentation.client_observations.models import ObservationBatchBody

NOW = datetime(2026, 11, 10, tzinfo=UTC).isoformat()


def event() -> dict[str, object]:
    return {
        "kind": "quality.observed",
        "event_id": str(uuid4()),
        "observed_at": NOW,
        "screen": "study",
        "reason": "unavailable",
        "count": 1,
    }


def batch(events: list[dict[str, object]]) -> dict[str, object]:
    return {"schema_version": 1, "events": events}


@pytest.mark.parametrize(
    "private_field", ["body", "query", "chat", "draft", "message", "stack", "url", "email", "props"]
)
def test_extra_private_context_has_no_wire_slot(private_field: str) -> None:
    supplied = event()
    supplied[private_field] = "private sentinel"
    with pytest.raises(ValidationError):
        ObservationBatchBody.model_validate(batch([supplied]))


@pytest.mark.parametrize("count", [True, "2", 0, -1, 65536, 1.5])
def test_quality_count_is_strict_bounded_integer(count: object) -> None:
    supplied = event()
    supplied["count"] = count
    with pytest.raises(ValidationError):
        ObservationBatchBody.model_validate(batch([supplied]))


def test_actor_changed_never_rebinds_old_quality_counts() -> None:
    supplied = event()
    supplied["reason"] = "actor_changed"
    with pytest.raises(ValidationError):
        ObservationBatchBody.model_validate(batch([supplied]))
    supplied["reason"] = "exhausted"
    assert (
        ObservationBatchBody.model_validate(batch([supplied])).observations()[0].parts()[0]
        == "quality.observed"
    )


def test_batch_size_distinct_ids_and_schema_are_strict() -> None:
    assert (
        len(ObservationBatchBody.model_validate(batch([event() for _ in range(MAX_EVENTS)])).events)
        == MAX_EVENTS
    )
    with pytest.raises(ValidationError):
        ObservationBatchBody.model_validate(batch([event() for _ in range(MAX_EVENTS + 1)]))
    duplicate = event()
    with pytest.raises(ValidationError):
        ObservationBatchBody.model_validate(batch([duplicate, duplicate]))
    with pytest.raises(ValidationError):
        ObservationBatchBody.model_validate({"schema_version": True, "events": [event()]})
