"""Worker root passes owned SDKs without touching credentials, SQL or providers."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import SecretStr

from studymate import bootstrap
from studymate.application.media.storage import MediaStorage
from studymate.config import AiWorkerRuntimeConfiguration, AiWorkerSettings, MediaConfiguration
from studymate.infrastructure.ai.runtime.factory import AiWorkerRuntime
from studymate.infrastructure.ai.telemetry import ObservedAiStep
from studymate.infrastructure.observability.runtime import TelemetryRuntime
from studymate.infrastructure.observability.tracing import OtelHttpTracing
from tests.integration.media_fixture import Storage
from tests.unit.ai.runtime.test_factory import configuration


def settings(root: Path) -> AiWorkerSettings:
    inputs = configuration(root)
    return AiWorkerSettings(
        _env_file=None,
        database_url=SecretStr("postgresql+asyncpg://synthetic:synthetic@127.0.0.1:1/worker_test"),
        media=MediaConfiguration(
            endpoint_origin="https://storage.example.test",
            bucket="synthetic-bucket",
            region="test-region",
            access_key_id=SecretStr("synthetic"),
            secret_access_key=SecretStr("synthetic"),
        ),
        runtime=AiWorkerRuntimeConfiguration(
            executable=inputs.executable,
            expected_version=inputs.expected_version,
            expected_sha256=inputs.expected_sha256,
            model=inputs.model,
            credential_directory=inputs.credential_directory,
            expected_account=SecretStr(inputs.expected_account),
            expected_login_owner=SecretStr(inputs.expected_login_owner),
            expected_oauth_issuer=inputs.expected_oauth_issuer,
            expected_oauth_client_id=inputs.expected_oauth_client_id,
            workspaces_root=inputs.workspaces_root,
            acceptance_artifact=inputs.acceptance_artifact,
            bubblewrap=inputs.bubblewrap,
            prlimit=inputs.prlimit,
        ),
    )


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("failed", [False, True])
async def test_worker_root_owns_optional_signals_and_shutdown_on_runtime_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, enabled: bool, failed: bool
) -> None:
    providers = TelemetryRuntime(
        OtelHttpTracing(),
        TracerProvider(shutdown_on_exit=False),
        MeterProvider(shutdown_on_exit=False),
    )
    exported = InMemorySpanExporter()
    providers.tracer_provider.add_span_processor(SimpleSpanProcessor(exported))
    closed: list[str] = []
    original_shutdown = TelemetryRuntime.shutdown
    stop = asyncio.Event()

    @asynccontextmanager
    async def storage(_configuration: MediaConfiguration | None) -> AsyncIterator[MediaStorage]:
        try:
            yield Storage(b"synthetic")
        finally:
            closed.append("storage")

    async def shutdown(runtime: TelemetryRuntime) -> None:
        closed.append("telemetry")
        await original_shutdown(runtime)

    async def run(runtime: AiWorkerRuntime, actual_stop: asyncio.Event) -> None:
        assert actual_stop is stop
        assert isinstance(runtime.supervisor.step, ObservedAiStep) is enabled
        assert (runtime.signals is not None) is enabled
        if enabled:
            assert isinstance(runtime.supervisor.step, ObservedAiStep)
            assert runtime.supervisor.step.tracer is not None
            with runtime.supervisor.step.tracer.start_as_current_span("root.wiring"):
                pass
            assert [span.name for span in exported.get_finished_spans()] == ["root.wiring"]
        if failed:
            raise RuntimeError("controlled runtime failure")

    monkeypatch.setattr(bootstrap, "_telemetry", lambda *_args: providers if enabled else None)
    monkeypatch.setattr(bootstrap, "_open_media_storage", storage)
    monkeypatch.setattr(AiWorkerRuntime, "run", run)
    monkeypatch.setattr(TelemetryRuntime, "shutdown", shutdown)
    try:
        if failed:
            with pytest.raises(RuntimeError, match="controlled runtime failure"):
                await bootstrap.run_ai_worker(settings(tmp_path), stop)
        else:
            await bootstrap.run_ai_worker(settings(tmp_path), stop)
        assert closed == (["storage", "telemetry"] if enabled else ["storage"])
        assert not (tmp_path / "private-auth").exists()
    finally:
        if not enabled:
            await original_shutdown(providers)
