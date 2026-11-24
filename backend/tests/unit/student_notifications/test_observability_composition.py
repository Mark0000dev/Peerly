"""Actual bootstrap with offline SDK/HTTP and typed loop ports; no PostgreSQL IO."""

import asyncio

import httpx2 as httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace import TracerProvider
from pydantic import SecretStr
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from studymate import bootstrap
from studymate.application.errors import StorageUnavailableError
from studymate.application.student_notifications.worker import (
    ConsumeStudentEvents,
    DeliverNextStudentNotification,
    PushDelivery,
)
from studymate.config import ObservabilityConfiguration
from studymate.domain.student_notifications.delivery import Claim, Delivery, Outcome
from studymate.infrastructure.observability.database import DatabaseTelemetry
from studymate.infrastructure.observability.runtime import TelemetryRuntime
from studymate.infrastructure.observability.student_notifications import (
    NotificationSnapshot,
    SqlStudentNotificationReader,
    StudentNotificationSignals,
)
from studymate.infrastructure.observability.tracing import OtelHttpTracing
from studymate.infrastructure.student_notifications.providers import (
    FcmConfiguration,
    ProviderSelection,
)
from studymate.infrastructure.student_notifications.settings import (
    StudentNotificationDeliverySettings,
)
from studymate.presentation.student_notifications.worker import (
    RunStudentNotifications,
    StudentWorkerObservation,
)

DATABASE = "postgresql+asyncpg://synthetic:synthetic@127.0.0.1:1/notification_test"
RELEASE = "a" * 40
SOURCE_BATCH = 50


def settings() -> StudentNotificationDeliverySettings:
    return StudentNotificationDeliverySettings(
        database_url=SecretStr(DATABASE), envelope_key=SecretStr("01" * 32)
    )


def test_explicit_nested_observability_environment_reuses_current_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "STUDENT_NOTIFICATIONS_OBSERVABILITY__COLLECTOR_ORIGIN", "http://127.0.0.1:4318"
    )
    monkeypatch.setenv("STUDENT_NOTIFICATIONS_OBSERVABILITY__ENVIRONMENT", "test")
    monkeypatch.setenv("STUDENT_NOTIFICATIONS_OBSERVABILITY__RELEASE", RELEASE)
    value = settings()
    assert value.observability == ObservabilityConfiguration(
        collector_origin="http://127.0.0.1:4318", environment="test", release=RELEASE
    )


async def test_configured_entrypoint_forwards_actual_observability_and_explicit_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = settings().model_copy(
        update={
            "observability": ObservabilityConfiguration(
                collector_origin="http://127.0.0.1:4318",
                environment="test",
                release=RELEASE,
            )
        }
    )
    selected = ProviderSelection()
    seen: list[ObservabilityConfiguration | None] = []

    def select_keys(material: object) -> ProviderSelection:
        assert material is not None
        return selected

    async def run(
        configuration: object,
        selection: ProviderSelection,
        envelope_key: bytes,
        stop: asyncio.Event,
        *,
        observability: ObservabilityConfiguration | None = None,
    ) -> None:
        assert configuration is value
        assert selection is selected
        assert envelope_key == bytes.fromhex("01" * 32)
        assert not stop.is_set()
        seen.append(observability)

    monkeypatch.setattr(bootstrap, "selection_from_keys", select_keys)
    monkeypatch.setattr(bootstrap, "run_student_delivery_worker", run)
    await bootstrap.run_configured_student_notifications(value, asyncio.Event())
    assert seen == [value.observability]


def offline_telemetry(history: list[str]) -> TelemetryRuntime:
    # SDK has no readers/exporters: no OTLP threads or network.
    class Runtime(TelemetryRuntime):
        async def shutdown(self) -> None:
            history.append("sdk")
            await super().shutdown()

    return Runtime(OtelHttpTracing(), TracerProvider(), MeterProvider())


def bind_observation_cleanup(
    monkeypatch: pytest.MonkeyPatch, history: list[str], client: httpx.AsyncClient
) -> None:
    original_close = DatabaseTelemetry.close

    def close_database(database: DatabaseTelemetry) -> None:
        assert client.is_closed
        history.append("hooks")
        original_close(database)

    signal_close = StudentNotificationSignals.close

    def close_signals(signals: StudentNotificationSignals) -> None:
        history.append("signals")
        signal_close(signals)

    async def snapshot(reader: SqlStudentNotificationReader) -> NotificationSnapshot:
        assert reader.sessions is not None
        # Exercise actual sampler outage handling without opening a connection.
        raise StorageUnavailableError

    monkeypatch.setattr(DatabaseTelemetry, "close", close_database)
    monkeypatch.setattr(StudentNotificationSignals, "close", close_signals)
    monkeypatch.setattr(SqlStudentNotificationReader, "snapshot", snapshot)


@pytest.mark.parametrize("termination", ["normal", "storage", "error", "cancel"])
async def test_actual_composition_retires_sampler_client_hooks_engine_before_sdk(
    termination: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    history: list[str] = []
    stop = asyncio.Event()
    engine = create_async_engine(DATABASE, pool_size=1, max_overflow=0)
    event.listen(engine.sync_engine, "engine_disposed", lambda _engine: history.append("engine"))

    telemetry = offline_telemetry(history)

    def make_telemetry(
        configuration: ObservabilityConfiguration | None,
        service_name: str = "studymate-api",
    ) -> TelemetryRuntime:
        assert configuration is not None
        assert service_name == "peerly-student-notifications-worker"
        return telemetry

    def make_engine(configuration: object) -> AsyncEngine:
        assert configuration is not None
        return engine

    def no_http(request: httpx.Request) -> httpx.Response:
        assert request.url.host is not None
        raise AssertionError("No HTTP request is authorized in bootstrap composition contract")

    client = httpx.AsyncClient(transport=httpx.MockTransport(no_http), trust_env=False)

    def make_client(selection: ProviderSelection) -> httpx.AsyncClient:
        assert selection.fcm is not None
        return client

    bind_observation_cleanup(monkeypatch, history, client)

    class Consumer:
        async def materialize(self, limit: int = 50) -> int:
            assert limit == SOURCE_BATCH
            if termination != "normal":
                stop.set()
                if termination == "storage":
                    raise StorageUnavailableError
                if termination == "cancel":
                    raise asyncio.CancelledError
                raise RuntimeError("synthetic loop failure")
            return 0

    class Queue:
        async def claim(self) -> Claim | None:
            stop.set()
            return None

        async def authorize(self, claim: Claim) -> Delivery | None:
            assert claim.delivery.id is not None
            raise AssertionError("No queued delivery in bootstrap contract")

        async def finish(self, claim: Claim, outcome: Outcome) -> bool:
            assert claim.delivery.id is not None
            assert outcome in tuple(Outcome)
            raise AssertionError("No provider completion in bootstrap contract")

    def worker(
        sessions: async_sessionmaker[AsyncSession],
        transport: PushDelivery,
        observer: StudentWorkerObservation | None = None,
    ) -> RunStudentNotifications:
        assert isinstance(sessions, async_sessionmaker)
        assert observer is not None
        return RunStudentNotifications(
            ConsumeStudentEvents(Consumer()),
            DeliverNextStudentNotification(Queue(), transport),
            observer,
        )

    monkeypatch.setattr(bootstrap, "_telemetry", make_telemetry)
    monkeypatch.setattr(bootstrap, "_student_notification_engine", make_engine)
    monkeypatch.setattr(bootstrap, "student_notifications_worker", worker)
    monkeypatch.setattr(ProviderSelection, "client", make_client)
    selected = ProviderSelection(
        fcm=FcmConfiguration(
            rsa.generate_private_key(public_exponent=65537, key_size=2048),
            "synthetic-project",
            "synthetic@example.test",
        )
    )
    observation = ObservabilityConfiguration(
        collector_origin="http://127.0.0.1:4318", environment="test", release=RELEASE
    )
    try:
        if termination in ("error", "cancel"):
            with pytest.raises(RuntimeError if termination == "error" else asyncio.CancelledError):
                await bootstrap.run_student_delivery_worker(
                    settings(), selected, bytes(32), stop, observability=observation
                )
        else:
            await bootstrap.run_student_delivery_worker(
                settings(), selected, bytes(32), stop, observability=observation
            )
        assert client.is_closed
        assert (
            history.index("signals")
            < history.index("hooks")
            < history.index("engine")
            < history.index("sdk")
        )
    finally:
        await client.aclose()
        await engine.dispose()


@pytest.mark.parametrize("guard", ["no-provider", "invalid-envelope", "already-stopped"])
async def test_launch_guards_do_not_allocate_telemetry_or_engine(
    guard: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def telemetry_not_started(
        configuration: ObservabilityConfiguration | None,
        service_name: str = "studymate-api",
    ) -> TelemetryRuntime:
        assert configuration is None
        assert service_name == "peerly-student-notifications-worker"
        raise AssertionError("Launch guard allocated SDK")

    def engine_not_started(configuration: object) -> AsyncEngine:
        assert configuration is not None
        raise AssertionError("Launch guard allocated engine")

    monkeypatch.setattr(bootstrap, "_telemetry", telemetry_not_started)
    monkeypatch.setattr(bootstrap, "_student_notification_engine", engine_not_started)
    stop = asyncio.Event()
    if guard == "already-stopped":
        stop.set()
        await bootstrap.run_student_delivery_worker(
            settings(), ProviderSelection(), bytes(32), stop
        )
        return
    selected = ProviderSelection()
    if guard == "invalid-envelope":
        selected = ProviderSelection(
            fcm=FcmConfiguration(
                rsa.generate_private_key(public_exponent=65537, key_size=2048),
                "synthetic-project",
                "synthetic@example.test",
            )
        )
    with pytest.raises(ValueError, match=r"No student delivery provider|envelope key"):
        await bootstrap.run_student_delivery_worker(
            settings(),
            selected,
            b"" if guard == "invalid-envelope" else bytes(32),
            stop,
        )
