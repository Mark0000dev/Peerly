"""Production resources are composed explicitly; invalid proof precedes credential access."""

import asyncio
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from studymate.infrastructure.ai.runtime import factory
from studymate.infrastructure.ai.runtime.acceptance import RuntimeAcceptanceError
from studymate.infrastructure.ai.runtime.factory import (
    AiRuntimeConfiguration,
    create_ai_validation_runtime,
    create_ai_worker_runtime,
)
from studymate.infrastructure.ai.runtime.policy import INSPECTED_SHA256, INSPECTED_VERSION
from studymate.infrastructure.ai.runtime.preflight import PinnedCli
from tests.integration.media_fixture import Storage


def configuration(root: Path) -> AiRuntimeConfiguration:
    return AiRuntimeConfiguration(
        Path("/usr/bin/synthetic-codex"),
        INSPECTED_VERSION,
        INSPECTED_SHA256,
        "synthetic-model",
        root / "private-auth",
        "synthetic-account",
        "synthetic-login",
        "synthetic-issuer",
        "synthetic-client",
        root / "jobs",
        Path("/usr/bin/bwrap"),
        Path("/usr/bin/prlimit"),
        root / "proof.json",
    )


async def test_production_cannot_read_credentials_or_register_ready_before_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def verify(_self: PinnedCli) -> None:
        return None

    async def reject(*_args: object, **_kwargs: object) -> object:
        raise RuntimeAcceptanceError("controlled missing deployment proof")

    monkeypatch.setattr(PinnedCli, "verify", verify)
    monkeypatch.setattr(factory, "validate_runtime_receipt", reject)
    runtime = create_ai_worker_runtime(
        async_sessionmaker(), Storage(b"synthetic"), configuration(tmp_path)
    )
    # No credential directory or DB connection exists: touching either would fail differently.
    with pytest.raises(RuntimeAcceptanceError):
        await runtime.run(asyncio.Event())
    assert not (tmp_path / "private-auth").exists()


def test_validation_has_no_readiness_or_queue_authority(tmp_path: Path) -> None:
    runtime = create_ai_validation_runtime(Storage(b"synthetic"), configuration(tmp_path))
    assert not hasattr(runtime, "health")
    assert not hasattr(runtime, "queue")


async def test_graceful_runtime_revokes_before_retiring_current_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from studymate.domain.ai.jobs import AiJob
    from studymate.infrastructure.ai.credentials import DedicatedCredentialCache
    from studymate.infrastructure.ai.queue import SqlAiQueue
    from studymate.infrastructure.ai.runtime.health import SqlRuntimeHealth

    steps: list[str] = []
    ready = asyncio.Event()

    async def verify(_self: PinnedCli) -> None:
        return None

    async def receipt(*_args: object, **_kwargs: object) -> object:
        return object()

    async def cache_ready(_self: DedicatedCredentialCache) -> None:
        steps.append("cache_validated")

    async def register(_self: SqlRuntimeHealth) -> None:
        steps.append("registered")

    async def heartbeat(_self: SqlRuntimeHealth, *, ready: bool = False) -> None:
        steps.append("ready" if ready else "heartbeat")
        if ready:
            signal_ready.set()

    async def revoke(_self: SqlRuntimeHealth, *, clean: bool) -> None:
        steps.append("retired" if clean else "revoked")

    async def recover(_self: SqlRuntimeHealth, queue: SqlAiQueue) -> None:
        assert queue.worker_id is not None
        steps.append("confirmed_cleanup")

    async def idle(_self: SqlAiQueue) -> AiJob | None:
        return None

    signal_ready = ready
    monkeypatch.setattr(PinnedCli, "verify", verify)
    monkeypatch.setattr(factory, "validate_runtime_receipt", receipt)
    monkeypatch.setattr(DedicatedCredentialCache, "validate_ready", cache_ready)
    monkeypatch.setattr(SqlRuntimeHealth, "register", register)
    monkeypatch.setattr(SqlRuntimeHealth, "heartbeat", heartbeat)
    monkeypatch.setattr(SqlRuntimeHealth, "revoke", revoke)
    monkeypatch.setattr(SqlRuntimeHealth, "recover_current_stopped", recover)
    monkeypatch.setattr(SqlAiQueue, "claim", idle)
    runtime = create_ai_worker_runtime(
        async_sessionmaker(), Storage(b"synthetic"), configuration(tmp_path)
    )
    stop = asyncio.Event()
    task = asyncio.create_task(runtime.run(stop))
    await ready.wait()
    stop.set()
    await task
    assert steps == [
        "cache_validated",
        "registered",
        "ready",
        "revoked",
        "confirmed_cleanup",
        "retired",
    ]


async def test_pending_receipt_shutdown_never_reads_credentials_or_registers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from studymate.infrastructure.ai.runtime.acceptance import RuntimeReceiptPendingError

    waiting = asyncio.Event()

    async def verify(_self: PinnedCli) -> None:
        return None

    async def pending(*_args: object, **_kwargs: object) -> object:
        waiting.set()
        raise RuntimeReceiptPendingError("controlled pending proof")

    monkeypatch.setattr(PinnedCli, "verify", verify)
    monkeypatch.setattr(factory, "validate_runtime_receipt", pending)
    runtime = create_ai_worker_runtime(
        async_sessionmaker(), Storage(b"synthetic"), configuration(tmp_path)
    )
    stop = asyncio.Event()
    running = asyncio.create_task(runtime.run(stop))
    await waiting.wait()
    stop.set()
    await running
    assert not (tmp_path / "private-auth").exists()


def test_worker_preserves_optional_same_transaction_report_guard(tmp_path: Path) -> None:
    from tests.unit.ai.test_report_guard import Guard

    guard = Guard(None)
    sessions = async_sessionmaker()
    runtime = create_ai_worker_runtime(
        sessions, Storage(b"synthetic"), configuration(tmp_path), reports=guard
    )
    assert runtime.queue.reports is guard
    assert runtime.queue.sessions is sessions
    assert runtime.health.sessions is sessions
    assert runtime.health.report_guard_version == 1
    assert guard.calls == []
    default = create_ai_worker_runtime(sessions, Storage(b"synthetic"), configuration(tmp_path))
    assert default.queue.reports is None
    assert default.health.report_guard_version is None
