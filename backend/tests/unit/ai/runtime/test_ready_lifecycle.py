"""Readiness logs follow successful ownership persistence, never idle iterations."""

import asyncio
import json
import logging
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from studymate.application.errors import StorageUnavailableError
from studymate.domain.ai.jobs import AiJob
from studymate.infrastructure.ai.credentials import DedicatedCredentialCache
from studymate.infrastructure.ai.queue import SqlAiQueue
from studymate.infrastructure.ai.runtime import factory
from studymate.infrastructure.ai.runtime.acceptance import RuntimeAcceptanceError
from studymate.infrastructure.ai.runtime.factory import create_ai_worker_runtime
from studymate.infrastructure.ai.runtime.health import RuntimeOwnershipError, SqlRuntimeHealth
from studymate.infrastructure.ai.runtime.preflight import PinnedCli
from studymate.infrastructure.observability.logging import LogEvent, SafeJsonFormatter
from tests.integration.media_fixture import Storage
from tests.unit.ai.runtime.test_factory import configuration

PRIVATE = "PRIVATE_MODEL_ACCOUNT_CACHE_JOB_TOKEN"
RELEASE = "a" * 40
IDLE_ITERATIONS = 3
RENEW_ITERATIONS = 2


def ready_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [
        record
        for record in caplog.records
        if getattr(record, "event", None) == LogEvent.WORKER_STEP
        and getattr(record, "outcome", None) == "ready"
    ]


class Lifecycle:
    """Controlled external boundaries; real composition, renewal and supervisor run."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.failure_at = ""
        self.failure: BaseException = StorageUnavailableError(PRIVATE)
        self.steps: list[str] = []
        self.ready_pending = asyncio.Event()
        self.complete_ready = asyncio.Event()
        self.idle_repeated = asyncio.Event()
        self.renewed_repeated = asyncio.Event()
        self.idle_count = 0
        self.renew_count = 0

        async def verify(_self: PinnedCli) -> None:
            self.steps.append("verify")

        async def receipt(*_args: object, **_kwargs: object) -> object:
            self.stage("receipt")
            return object()

        async def cache(_self: DedicatedCredentialCache) -> None:
            self.stage("cache")

        async def register(_self: SqlRuntimeHealth) -> None:
            self.stage("register")

        async def heartbeat(_self: SqlRuntimeHealth, *, ready: bool = False) -> None:
            if ready:
                self.ready_pending.set()
                await self.complete_ready.wait()
                # Returning stands for successful transaction exit, including commit.
                self.stage("ready_commit")
            else:
                self.renew_count += 1
                if self.renew_count >= RENEW_ITERATIONS:
                    self.renewed_repeated.set()

        async def revoke(_self: SqlRuntimeHealth, *, clean: bool) -> None:
            self.steps.append("retired" if clean else "revoked")

        async def recover(_self: SqlRuntimeHealth, _queue: SqlAiQueue) -> None:
            self.steps.append("cleanup")

        async def idle(_self: SqlAiQueue) -> AiJob | None:
            self.idle_count += 1
            if self.idle_count >= IDLE_ITERATIONS:
                self.idle_repeated.set()
            return None

        monkeypatch.setattr(PinnedCli, "verify", verify)
        monkeypatch.setattr(factory, "validate_runtime_receipt", receipt)
        monkeypatch.setattr(DedicatedCredentialCache, "validate_ready", cache)
        monkeypatch.setattr(SqlRuntimeHealth, "register", register)
        monkeypatch.setattr(SqlRuntimeHealth, "heartbeat", heartbeat)
        monkeypatch.setattr(SqlRuntimeHealth, "revoke", revoke)
        monkeypatch.setattr(SqlRuntimeHealth, "recover_current_stopped", recover)
        monkeypatch.setattr(SqlAiQueue, "claim", idle)
        monkeypatch.setattr(factory, "RUNTIME_HEARTBEAT_SECONDS", 0.001)

    def stage(self, name: str) -> None:
        self.steps.append(name)
        if self.failure_at == name:
            raise self.failure


async def test_ready_once_after_successful_commit_not_during_idle_or_renewal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    scenario = Lifecycle(monkeypatch)
    runtime = create_ai_worker_runtime(
        async_sessionmaker(), Storage(PRIVATE.encode()), configuration(tmp_path)
    )
    runtime.supervisor.poll_seconds = 0.001
    stop = asyncio.Event()
    with caplog.at_level(logging.INFO, logger=factory.__name__):
        running = asyncio.create_task(runtime.run(stop))
        try:
            await asyncio.wait_for(scenario.ready_pending.wait(), 2)
            assert scenario.steps == ["verify", "receipt", "cache", "register"]
            assert ready_records(caplog) == []
            scenario.complete_ready.set()
            await asyncio.wait_for(scenario.idle_repeated.wait(), 2)
            await asyncio.wait_for(scenario.renewed_repeated.wait(), 2)
            records = ready_records(caplog)
            assert len(records) == 1
            record = records[0]
            assert scenario.steps[:5] == ["verify", "receipt", "cache", "register", "ready_commit"]
            assert record.levelno == logging.INFO
            assert record.msg == LogEvent.WORKER_STEP
            assert record.args == ()
            assert record.exc_info is None
            encoded = SafeJsonFormatter(release=RELEASE).format(record)
            content = json.loads(encoded)
            assert set(content) == {"time", "level", "event", "outcome", "service_release"}
            assert content["event"] == "worker_step"
            assert content["outcome"] == "ready"
            assert content["service_release"] == RELEASE
            assert PRIVATE not in encoded
            assert PRIVATE not in repr(record.__dict__)
        finally:
            scenario.complete_ready.set()
            stop.set()
            await asyncio.wait_for(running, 2)
    assert len(ready_records(caplog)) == 1
    assert scenario.steps[-3:] == ["revoked", "cleanup", "retired"]


@pytest.mark.parametrize(
    ("stage", "error"),
    [
        ("receipt", RuntimeAcceptanceError(PRIVATE)),
        ("cache", RuntimeError(PRIVATE)),
        ("register", RuntimeOwnershipError(PRIVATE)),
        ("ready_commit", RuntimeOwnershipError(PRIVATE)),
        ("ready_commit", StorageUnavailableError(PRIVATE)),
        ("ready_commit", asyncio.CancelledError(PRIVATE)),
    ],
)
async def test_no_ready_event_when_readiness_rejected_or_transaction_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    stage: str,
    error: BaseException,
) -> None:
    scenario = Lifecycle(monkeypatch)
    scenario.failure_at = stage
    scenario.failure = error
    scenario.complete_ready.set()
    runtime = create_ai_worker_runtime(
        async_sessionmaker(), Storage(PRIVATE.encode()), configuration(tmp_path)
    )
    with (
        caplog.at_level(logging.INFO, logger=factory.__name__),
        pytest.raises(type(error)) as caught,
    ):
        await asyncio.wait_for(runtime.run(asyncio.Event()), 2)
    assert caught.value is error
    assert ready_records(caplog) == []
    assert scenario.idle_count == 0
    assert scenario.renew_count == 0
    assert PRIVATE not in caplog.text
    assert not runtime._active
