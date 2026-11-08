import json
from pathlib import Path
from typing import NoReturn

import httpx2
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

import studymate.export_openapi as exporter
from studymate import bootstrap


async def test_enabled_schema_is_deterministic_without_provider_or_database_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def deny_connection(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("Schema export attempted database I/O")

    async def deny_provider(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("Schema export attempted provider I/O")

    monkeypatch.setattr(AsyncEngine, "connect", deny_connection)
    monkeypatch.setattr(httpx2.AsyncClient, "send", deny_provider)
    first = json.dumps(await exporter.build_schema(), sort_keys=True)
    assert first == json.dumps(await exporter.build_schema(), sort_keys=True)
    assert "/api/v1/auth/google/start" in first
    assert "/api/v1/auth/email-challenges/{challenge_id}/verify" in first
    assert "Idempotency-Key" in first or "idempotency-key" in first
    assert "SessionCookie" in first
    assert "/api/v1/events" in first
    assert "text/event-stream" in first
    assert "/api/v1/discovery" in first
    assert "/api/v1/discovery/passes/{person_id}" in first
    assert "DiscoveryPageResponse" in first
    assert "/api/v1/requests" in first
    assert "/api/v1/requests/{request_id}/viewed" in first
    assert "RequestPageResponse" in first
    assert "/api/v1/conversations/{conversation_id}/messages" in first
    assert "/api/v1/conversations/{conversation_id}/participant" in first
    assert "/api/v1/conversations/{conversation_id}/read-position" in first
    assert "ConversationDetailsResponse" in first
    assert "ConversationListResponse" in first
    assert "MessageHistoryResponse" in first
    assert "/api/v1/conversations/{conversation_id}/goal-shares" in first
    assert "/api/v1/people/{person_id}" in first
    assert "/api/v1/me/blocks" in first
    assert "/api/v1/reports" in first
    assert "/api/v1/operator/accounts/{account_id}/help-history" in first
    assert "/api/v1/operator/accounts/{account_id}/goals" in first
    assert "/api/v1/operator/accounts/{account_id}/goals/{goal_id}/history" in first
    assert "/api/v1/operator/reports" in first
    assert "/api/v1/operator/reports/{report_id}" in first
    assert "/api/v1/operator/accounts/{account_id}/profile-history" in first
    assert "/api/v1/operator/accounts/{account_id}/ai-jobs" in first
    assert "/api/v1/operator/accounts/{account_id}/ai-jobs/{job_id}" in first
    assert "/api/v1/operator/accounts/{account_id}/photo-uploads" in first
    assert "/api/v1/operator/accounts/{account_id}/photo-uploads/{upload_id}/history" in first
    assert "/attempts/{attempt_id}/{kind}" in first
    assert "/api/v1/ai/jobs" in first
    assert "/api/v1/ai/jobs/{job_id}/cancel" in first
    assert "ProblemResponse" in first
    assert "synthetic-schema-secret" not in first
    assert "01" * 32 not in first


def test_export_cli_stdout_and_file_are_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    async def synthetic_schema() -> dict[str, object]:
        return {"openapi": "synthetic-test-document"}

    monkeypatch.setattr(exporter, "build_schema", synthetic_schema)
    exporter.main([])
    assert json.loads(capsys.readouterr().out) == {"openapi": "synthetic-test-document"}
    target = tmp_path / "openapi.json"
    exporter.main(["--output", str(target)])
    assert json.loads(target.read_text()) == {"openapi": "synthetic-test-document"}


async def test_schema_export_does_not_activate_environment_media_or_telemetry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("Schema export tried to configure a real integration")

    monkeypatch.setenv("MEDIA__ENDPOINT_ORIGIN", "https://storage.example.test")
    monkeypatch.setenv("MEDIA__BUCKET", "synthetic-bucket")
    monkeypatch.setenv("MEDIA__REGION", "us-east-1")
    monkeypatch.setenv("MEDIA__ACCESS_KEY_ID", "synthetic-identifier")
    monkeypatch.setenv("MEDIA__SECRET_ACCESS_KEY", "synthetic-signing-material")
    monkeypatch.setenv("OBSERVABILITY__COLLECTOR_ORIGIN", "https://collector.example.test")
    monkeypatch.setenv("OBSERVABILITY__ENVIRONMENT", "synthetic")
    monkeypatch.setenv("OBSERVABILITY__RELEASE", "test")
    monkeypatch.setattr(bootstrap, "_open_media_storage", unexpected)
    monkeypatch.setattr(bootstrap, "build_telemetry", unexpected)
    assert (await exporter.build_schema())["openapi"]


async def test_student_feedback_export_uses_only_the_actual_closed_problem_contract() -> None:
    first = json.dumps(await exporter.build_schema(), sort_keys=True)
    assert "/api/v1/conversations/{conversation_id}/study-outcome" in first
    assert "/api/v1/conversations/{conversation_id}/feedback" in first
    assert "/api/v1/conversations/{conversation_id}/study-prompt-visits" in first
    assert "/api/v1/me/feedback-summary" in first
    assert "/api/v1/people/{person_id}/feedback-summary" in first
    assert "HTTPValidationError" not in first
    assert '"ValidationError"' not in first
