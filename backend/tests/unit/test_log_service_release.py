from __future__ import annotations

import io
import json
import logging
from typing import TYPE_CHECKING, Never

import pytest

from studymate import bootstrap
from studymate.config import ObservabilityConfiguration
from studymate.infrastructure.ai.runtime.diagnostics import (
    AiRuntimeCode,
    AiRuntimeDiagnostic,
    AiRuntimePhase,
)
from studymate.infrastructure.observability.logging import (
    SafeJsonFormatter,
    bind_log_release,
    validated_service_release,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from studymate.infrastructure.observability.runtime import TelemetryConfiguration

CORE = "a" * 40
AI = "b" * 40
PRIVATE = "private-cookie-dsn-token-message-value"


def record() -> logging.LogRecord:
    return logging.LogRecord(
        "studymate.test", logging.ERROR, __file__, 1, PRIVATE, (PRIVATE,), None
    )


@pytest.fixture
def owned_formatter() -> Iterator[SafeJsonFormatter]:
    handler = logging.StreamHandler(io.StringIO())
    formatter = SafeJsonFormatter()
    handler.setFormatter(formatter)
    logger = logging.getLogger("uvicorn")
    logger.addHandler(handler)
    try:
        yield formatter
    finally:
        logger.removeHandler(handler)
        handler.close()


def test_explicit_formatter_versions_are_separate_and_record_cannot_override_them() -> None:
    event = record()
    event.service_release = "c" * 40
    api, ai = SafeJsonFormatter(release=CORE), SafeJsonFormatter(release=AI)
    assert json.loads(api.format(event))["service_release"] == CORE
    assert json.loads(ai.format(event))["service_release"] == AI
    assert "service_release" not in json.loads(SafeJsonFormatter().format(event))
    assert PRIVATE not in api.format(event)


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        123,
        {},
        [],
        "",
        "v1",
        "0" * 40,
        "A" * 40,
        "a" * 39,
        "a" * 41,
        "a" * 40 + "\n",
        "\uff41" * 40,
        PRIVATE,
    ],
)
def test_only_nonzero_lowercase_full_sha_is_accepted(value: object) -> None:
    assert validated_service_release(value) is None


def test_release_and_safe_ai_diagnostics_coexist_without_untrusted_record_fields() -> None:
    event = record()
    phase, code = next(iter(AiRuntimePhase)), next(iter(AiRuntimeCode))
    event.ai_runtime_diagnostic = AiRuntimeDiagnostic(phase, code, True)
    output = SafeJsonFormatter(release=AI).format(event)
    value = json.loads(output)
    assert value["service_release"] == AI
    assert value["ai_runtime_code"] == code.value
    assert value["ai_runtime_phase"] == phase.value
    assert PRIVATE not in output


def test_binding_does_not_replace_handlers_levels_or_foreign_formatters(
    owned_formatter: SafeJsonFormatter,
) -> None:
    logger = logging.getLogger("uvicorn")
    handlers, level = tuple(logger.handlers), logger.level
    bind_log_release(CORE)
    assert tuple(logger.handlers) == handlers
    assert logger.level == level
    assert json.loads(owned_formatter.format(record()))["service_release"] == CORE
    bind_log_release(None)
    assert "service_release" not in json.loads(owned_formatter.format(record()))


class StopSdkError(RuntimeError):
    pass


@pytest.mark.parametrize(
    ("name", "release"),
    [
        ("studymate-api", CORE),
        ("studymate-email-worker", CORE),
        ("studymate-media-worker", CORE),
        ("peerly-requests-worker", CORE),
        ("peerly-changes-worker", CORE),
        ("peerly-external-delivery-worker", CORE),
        ("studymate-ai-worker", AI),
    ],
)
def test_actual_settings_bind_before_sdk_startup_for_each_service(
    name: str,
    release: str,
    owned_formatter: SafeJsonFormatter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configuration = ObservabilityConfiguration(
        collector_origin="http://collector.example.test:4318",
        environment="test",
        release=release,
    )

    def stop_sdk(value: TelemetryConfiguration) -> Never:
        assert value.service_name == name
        assert value.release == release
        assert json.loads(owned_formatter.format(record()))["service_release"] == release
        raise StopSdkError

    monkeypatch.setattr(bootstrap, "build_telemetry", stop_sdk)
    with pytest.raises(StopSdkError):
        bootstrap._telemetry(configuration, name)
    assert bootstrap._telemetry(None, name) is None
    assert "service_release" not in json.loads(owned_formatter.format(record()))
