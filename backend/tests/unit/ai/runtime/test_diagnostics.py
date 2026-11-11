"""Finite failure packets preserve original errors and fail-closed runtime teardown."""

import asyncio
import logging
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from studymate.application.errors import StorageUnavailableError
from studymate.domain.ai.jobs import AiJob
from studymate.infrastructure.ai.credentials import DedicatedCredentialCache
from studymate.infrastructure.ai.process import (
    CredentialStateUncertainError,
    TerminationUncertainError,
)
from studymate.infrastructure.ai.queue import SqlAiQueue
from studymate.infrastructure.ai.runtime import factory
from studymate.infrastructure.ai.runtime.acceptance import RuntimeAcceptanceError
from studymate.infrastructure.ai.runtime.diagnostics import (
    AiRuntimeCode,
    AiRuntimeDiagnostic,
    AiRuntimePhase,
)
from studymate.infrastructure.ai.runtime.factory import create_ai_worker_runtime
from studymate.infrastructure.ai.runtime.health import RuntimeOwnershipError, SqlRuntimeHealth
from studymate.infrastructure.ai.runtime.preflight import PinnedCli
from studymate.infrastructure.ai.runtime.supervisor import WorkerState
from tests.integration.media_fixture import Storage
from tests.unit.ai.runtime.test_factory import configuration

PRIVATE = "PRIVATE_SQL_URL_AUTH_SENTINEL"


def packets(caplog: pytest.LogCaptureFixture) -> list[AiRuntimeDiagnostic]:
    result = []
    for record in caplog.records:
        packet: object = getattr(record, "ai_runtime_diagnostic", None)
        if isinstance(packet, AiRuntimeDiagnostic):
            result.append(packet)
            assert record.exc_info is None
            assert not record.args
            assert PRIVATE not in repr(record.__dict__)
    return result


def test_packet_is_immutable_and_rejects_raw_phase_code_or_nonboolean() -> None:
    packet = AiRuntimeDiagnostic(AiRuntimePhase.HEARTBEAT, AiRuntimeCode.STORAGE_UNAVAILABLE, True)
    with pytest.raises(FrozenInstanceError):
        packet.__setattr__("primary", False)
    for changed in ({"phase": PRIVATE}, {"code": PRIVATE}, {"primary": 1}):
        with pytest.raises(ValueError, match="closed"):
            replace(packet, **changed)


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (StorageUnavailableError(PRIVATE), AiRuntimeCode.STORAGE_UNAVAILABLE),
        (RuntimeOwnershipError(PRIVATE), AiRuntimeCode.OWNERSHIP_LOST),
        (RuntimeAcceptanceError(PRIVATE), AiRuntimeCode.RECEIPT_REJECTED),
        (TerminationUncertainError(PRIVATE), AiRuntimeCode.PHYSICAL_STOP_UNCERTAIN),
        (CredentialStateUncertainError(), AiRuntimeCode.CREDENTIAL_UNCERTAIN),
        (asyncio.CancelledError(PRIVATE), AiRuntimeCode.CANCELLED),
        (RuntimeError(PRIVATE), AiRuntimeCode.UNEXPECTED),
    ],
)
async def test_all_codes_are_finite_and_the_same_exception_propagates(
    caplog: pytest.LogCaptureFixture,
    error: BaseException,
    code: AiRuntimeCode,
) -> None:
    async def failed() -> None:
        raise error

    with caplog.at_level(logging.ERROR), pytest.raises(type(error)) as captured:
        await factory._diagnosed(AiRuntimePhase.HEARTBEAT, failed())
    assert captured.value is error
    assert packets(caplog) == [AiRuntimeDiagnostic(AiRuntimePhase.HEARTBEAT, code, True)]
    assert PRIVATE not in caplog.text


async def test_normal_quiesced_heartbeat_cancellation_is_not_a_failure_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    quiesce = asyncio.Event()
    quiesce.set()

    async def cancelled() -> None:
        raise asyncio.CancelledError(PRIVATE)

    with pytest.raises(asyncio.CancelledError):
        await factory._diagnosed(AiRuntimePhase.HEARTBEAT, cancelled(), quiesce=quiesce)
    assert packets(caplog) == []


class SyntheticRuntime:
    """Patch only provider/SQL boundaries; actual factory/supervisor/teardown execute."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.primary = StorageUnavailableError(PRIVATE)
        self.secondary: BaseException | None = None
        self.claim_error: BaseException | None = None
        self.revocations: list[bool] = []
        self.clean_recoveries = 0
        self.patches(monkeypatch)

    def patches(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def verify(_self: PinnedCli) -> None:
            return None

        async def receipt(*_args: object, **_kwargs: object) -> object:
            return object()

        async def cache(_self: DedicatedCredentialCache) -> None:
            return None

        async def register(_self: SqlRuntimeHealth) -> None:
            return None

        async def heartbeat(_self: SqlRuntimeHealth, *, ready: bool = False) -> None:
            if not ready:
                raise self.primary

        async def revoke(_self: SqlRuntimeHealth, *, clean: bool) -> None:
            self.revocations.append(clean)
            if self.secondary is not None:
                raise self.secondary

        async def recover(_self: SqlRuntimeHealth, _queue: SqlAiQueue) -> None:
            self.clean_recoveries += 1

        async def claim(_self: SqlAiQueue) -> AiJob | None:
            if self.claim_error is not None:
                raise self.claim_error
            return None

        for target, name, replacement in (
            (PinnedCli, "verify", verify),
            (factory, "validate_runtime_receipt", receipt),
            (DedicatedCredentialCache, "validate_ready", cache),
            (SqlRuntimeHealth, "register", register),
            (SqlRuntimeHealth, "heartbeat", heartbeat),
            (SqlRuntimeHealth, "revoke", revoke),
            (SqlRuntimeHealth, "recover_current_stopped", recover),
            (SqlAiQueue, "claim", claim),
        ):
            monkeypatch.setattr(target, name, replacement)
        monkeypatch.setattr(factory, "RUNTIME_HEARTBEAT_SECONDS", 0.001)


async def test_primary_heartbeat_record_survives_secondary_revoke_mask_without_new_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    scenario = SyntheticRuntime(monkeypatch)
    scenario.secondary = RuntimeOwnershipError(PRIVATE)
    runtime = create_ai_worker_runtime(
        async_sessionmaker(), Storage(b"synthetic"), configuration(tmp_path)
    )
    with caplog.at_level(logging.ERROR), pytest.raises(RuntimeOwnershipError) as captured:
        await runtime.run(asyncio.Event())
    assert captured.value is scenario.secondary
    assert packets(caplog) == [
        AiRuntimeDiagnostic(AiRuntimePhase.HEARTBEAT, AiRuntimeCode.STORAGE_UNAVAILABLE, True),
        AiRuntimeDiagnostic(AiRuntimePhase.REVOKE, AiRuntimeCode.OWNERSHIP_LOST, False),
    ]
    assert scenario.revocations == [False]
    assert scenario.clean_recoveries == 0
    assert not runtime._active
    assert PRIVATE not in caplog.text


@pytest.mark.parametrize(
    "uncertain", [TerminationUncertainError(PRIVATE), CredentialStateUncertainError()]
)
async def test_worker_uncertainty_is_reported_without_clean_retire_or_claim_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    uncertain: BaseException,
) -> None:
    scenario = SyntheticRuntime(monkeypatch)
    scenario.claim_error = uncertain
    runtime = create_ai_worker_runtime(
        async_sessionmaker(), Storage(b"synthetic"), configuration(tmp_path)
    )
    with caplog.at_level(logging.ERROR), pytest.raises(type(uncertain)) as captured:
        await runtime.run(asyncio.Event())
    assert captured.value is uncertain
    assert runtime.supervisor.state == WorkerState.BLOCKED
    assert scenario.revocations == [False]
    assert scenario.clean_recoveries == 0
    observed = packets(caplog)
    assert len(observed) == 1
    assert observed[0].phase == AiRuntimePhase.PHYSICAL_CLEANUP
    assert observed[0].primary


async def test_receipt_recheck_error_is_logged_before_any_heartbeat_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    SyntheticRuntime(monkeypatch)
    failure = RuntimeAcceptanceError(PRIVATE)

    async def reject(*_args: object, **_kwargs: object) -> object:
        raise failure

    monkeypatch.setattr(factory, "validate_runtime_receipt", reject)
    runtime = create_ai_worker_runtime(
        async_sessionmaker(), Storage(b"synthetic"), configuration(tmp_path)
    )
    with caplog.at_level(logging.ERROR), pytest.raises(RuntimeAcceptanceError) as captured:
        await runtime._renew(asyncio.Event())
    assert captured.value is failure
    assert packets(caplog) == [
        AiRuntimeDiagnostic(AiRuntimePhase.RECEIPT_RECHECK, AiRuntimeCode.RECEIPT_REJECTED, True)
    ]
