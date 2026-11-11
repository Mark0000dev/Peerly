"""The optional resource revision is bounded and never raises the default."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from studymate.config import AiWorkerRuntimeConfiguration
from tests.unit.test_ai_worker_telemetry_composition import settings

DEFAULT_PROCESS_LIMIT = 32
EXPLICIT_PROCESS_LIMIT = 40


def test_worker_process_limit_preserves_default_and_accepts_explicit_bounded_revision(
    tmp_path: Path,
) -> None:
    runtime = settings(tmp_path).runtime
    assert runtime.max_processes == DEFAULT_PROCESS_LIMIT
    revised = AiWorkerRuntimeConfiguration.model_validate(
        runtime.model_dump() | {"max_processes": EXPLICIT_PROCESS_LIMIT}
    )
    assert revised.max_processes == EXPLICIT_PROCESS_LIMIT


@pytest.mark.parametrize("limit", [31, 41])
def test_worker_process_limit_rejects_values_outside_reviewed_resource_bounds(
    tmp_path: Path,
    limit: int,
) -> None:
    runtime = settings(tmp_path).runtime
    with pytest.raises(ValidationError, match="max_processes"):
        AiWorkerRuntimeConfiguration.model_validate(runtime.model_dump() | {"max_processes": limit})
