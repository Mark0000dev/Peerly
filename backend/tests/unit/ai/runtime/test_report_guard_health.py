"""Report capability is registered by composition, never inferred by heartbeat."""

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.domain.ai.jobs import Versions
from studymate.infrastructure.ai.models import AiSlotRecord
from studymate.infrastructure.ai.persistence import SqlAiTransaction
from studymate.infrastructure.ai.runtime import health as health_module
from studymate.infrastructure.ai.runtime.availability import require_runtime_ready
from studymate.infrastructure.ai.runtime.health import REPORT_GUARD_VERSION, SqlRuntimeHealth

AT = datetime(2026, 11, 12, tzinfo=UTC)
VERSIONS = Versions("synthetic-model")


@asynccontextmanager
async def transaction(_sessions: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with AsyncSession() as session:
        yield session


@contextmanager
def database(slot: AiSlotRecord) -> Iterator[None]:
    with (
        patch.object(health_module, "open_transaction", side_effect=transaction),
        patch.object(health_module, "lock_slot", return_value=slot),
        patch.object(SqlAiTransaction, "now", return_value=AT),
    ):
        yield


@pytest.mark.parametrize("version", [0, 2, -1, True])
def test_rejects_unimplemented_or_boolean_capability(version: int) -> None:
    with pytest.raises(ValueError, match="absent or version1"):
        SqlRuntimeHealth(async_sessionmaker(), uuid4(), VERSIONS, report_guard_version=version)


@pytest.mark.parametrize("version", [None, REPORT_GUARD_VERSION])
async def test_register_ready_retire_preserves_student_health_and_clears_fact(
    version: int | None,
) -> None:
    slot = AiSlotRecord(id=1, runtime_state="stopped")
    health = SqlRuntimeHealth(async_sessionmaker(), uuid4(), VERSIONS, version)
    with database(slot):
        await health.register()
        assert slot.runtime_report_guard_version == version
        await health.heartbeat(ready=True)
        assert require_runtime_ready(slot, AT) == VERSIONS
        assert slot.runtime_report_guard_version == version
        await health.revoke(clean=True)
    assert slot.runtime_state == "stopped"
    assert slot.runtime_worker_id is None
    assert slot.runtime_report_guard_version is None


async def test_heartbeat_cannot_upgrade_old_runtime_capability() -> None:
    slot = AiSlotRecord(id=1, runtime_state="stopped")
    health = SqlRuntimeHealth(async_sessionmaker(), uuid4(), VERSIONS)
    other_configuration = SqlRuntimeHealth(
        health.sessions, health.worker_id, VERSIONS, REPORT_GUARD_VERSION
    )
    with database(slot):
        await health.register()
        await other_configuration.heartbeat(ready=True)
    assert slot.runtime_report_guard_version is None
    assert require_runtime_ready(slot, AT) == VERSIONS


async def test_unclean_stop_retains_fact_but_revokes_ready_state() -> None:
    slot = AiSlotRecord(id=1, runtime_state="stopped")
    health = SqlRuntimeHealth(async_sessionmaker(), uuid4(), VERSIONS, REPORT_GUARD_VERSION)
    with database(slot):
        await health.register()
        await health.heartbeat(ready=True)
        await health.revoke(clean=False)
    assert slot.runtime_state == "blocked"
    assert slot.runtime_worker_id == health.worker_id
    assert slot.runtime_report_guard_version == REPORT_GUARD_VERSION


async def test_confirmed_predecessor_recovery_clears_report_guard_fact(tmp_path: Path) -> None:
    from studymate.infrastructure.ai.credentials import DedicatedCredentialCache
    from studymate.infrastructure.ai.runtime import recovery
    from studymate.infrastructure.ai.runtime.factory import create_ai_worker_runtime
    from tests.integration.media_fixture import Storage
    from tests.unit.ai.runtime.test_factory import configuration
    from tests.unit.ai.runtime.test_process_bound_receipts import receipt

    runtime = create_ai_worker_runtime(
        async_sessionmaker(), Storage(b"synthetic"), configuration(tmp_path)
    )
    proof = receipt(32)
    worker = uuid4()
    slot = AiSlotRecord(
        id=1,
        runtime_worker_id=worker,
        runtime_state="blocked",
        generation=1,
        token=None,
        runtime_report_guard_version=REPORT_GUARD_VERSION,
    )
    evidence = recovery.StoppedPredecessorEvidence(
        proof.deployment_id, worker, None, 1, datetime.now(UTC), "d" * 64, "e" * 64
    )
    with (
        patch.object(recovery, "validate_runtime_receipt", return_value=proof),
        patch.object(recovery, "open_transaction", side_effect=transaction),
        patch.object(recovery, "lock_slot", return_value=slot),
        patch.object(DedicatedCredentialCache, "validate_ready", return_value=None),
    ):
        await recovery.recover_stopped_predecessor(runtime, evidence)
    assert slot.runtime_state == "stopped"
    assert slot.runtime_worker_id is None
    assert slot.runtime_report_guard_version is None
