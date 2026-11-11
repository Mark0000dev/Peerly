"""The root drains/cancels the actual sampler before disposing worker-owned SDKs."""

import asyncio
from typing import NoReturn
from uuid import uuid4

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace import TracerProvider
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate import bootstrap
from studymate.config import ExternalDeliveryWorkerSettings, UmamiDeliveryConfiguration
from studymate.infrastructure.external_delivery.destinations import DestinationRegistration
from studymate.infrastructure.external_delivery.runtime import ExternalDeliveryWorker
from studymate.infrastructure.observability.delivery_queue import SqlDeliveryQueueReader
from studymate.infrastructure.observability.runtime import TelemetryRuntime
from studymate.infrastructure.observability.tracing import OtelHttpTracing


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("failed", [False, True])
async def test_root_sampler_drains_before_sdk_shutdown_and_is_absent_without_telemetry(
    monkeypatch: pytest.MonkeyPatch,
    enabled: bool,
    failed: bool,
) -> None:
    providers = TelemetryRuntime(
        OtelHttpTracing(),
        TracerProvider(shutdown_on_exit=False),
        MeterProvider(shutdown_on_exit=False),
    )
    stop = asyncio.Event()
    sample_started = asyncio.Event()
    sample_closed = asyncio.Event()
    never = asyncio.Event()
    closed: list[str] = []
    original_shutdown = TelemetryRuntime.shutdown

    async def register(
        _sessions: async_sessionmaker[AsyncSession],
        registrations: tuple[DestinationRegistration, ...],
    ) -> None:
        assert len(registrations) == 1

    async def snapshot(_self: SqlDeliveryQueueReader) -> NoReturn:
        sample_started.set()
        try:
            await never.wait()
        finally:
            sample_closed.set()
        raise AssertionError("A blocked sample must time out or be cancelled")

    async def work(_self: ExternalDeliveryWorker, actual_stop: asyncio.Event) -> None:
        assert actual_stop is stop
        if enabled:
            await sample_started.wait()
        if failed:
            raise RuntimeError("controlled worker failure")
        stop.set()

    async def shutdown(runtime: TelemetryRuntime) -> None:
        assert sample_closed.is_set() is enabled
        closed.append("sdk")
        await original_shutdown(runtime)

    monkeypatch.setattr(bootstrap, "_telemetry", lambda *_args: providers if enabled else None)
    monkeypatch.setattr(bootstrap, "register_destinations", register)
    monkeypatch.setattr(SqlDeliveryQueueReader, "snapshot", snapshot)
    monkeypatch.setattr(ExternalDeliveryWorker, "run", work)
    monkeypatch.setattr(TelemetryRuntime, "shutdown", shutdown)
    settings = ExternalDeliveryWorkerSettings(
        _env_file=None,
        database_url=SecretStr("postgresql+asyncpg://test:synthetic@127.0.0.1:1/worker_test"),
        umami=UmamiDeliveryConfiguration(
            revision=1,
            origin="https://analytics.test",
            website_id=uuid4(),
        ),
    )
    try:
        async with asyncio.timeout(2):
            if failed:
                with pytest.raises(ExceptionGroup if enabled else RuntimeError):
                    await bootstrap.run_external_delivery_worker(settings, stop)
            else:
                await bootstrap.run_external_delivery_worker(settings, stop)
        assert sample_started.is_set() is enabled
        assert closed == (["sdk"] if enabled else [])
    finally:
        if not enabled:
            await original_shutdown(providers)
