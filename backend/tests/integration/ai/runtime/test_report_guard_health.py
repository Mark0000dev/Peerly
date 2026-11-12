"""Real migrated PG capability lifecycle; definitions await the coordinated0060 batch.

No native/provider/auth calls. Guard injection is the actual operator adapter, not
an environment flag or permissive replacement. Existing student fixtures stay NULL.
"""

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.infrastructure.ai.models import AiSlotRecord
from studymate.infrastructure.ai.runtime.availability import require_runtime_ready
from studymate.infrastructure.ai.runtime.factory import create_ai_worker_runtime
from studymate.infrastructure.ai.runtime.health import REPORT_GUARD_VERSION, SqlRuntimeHealth
from tests.integration.ai.test_queue import VERSIONS
from tests.integration.media_fixture import Storage
from tests.unit.ai.runtime.test_factory import configuration

pytestmark = pytest.mark.integration


async def read_slot(sessions: async_sessionmaker[AsyncSession]) -> AiSlotRecord:
    async with sessions() as session:
        slot = await session.get(AiSlotRecord, 1)
        assert slot is not None
        return slot


async def test_old_null_guard_remains_student_ready_and_heartbeat_cannot_upgrade(
    identity_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    original = await read_slot(sessions)
    assert original.runtime_report_guard_version is None
    health = SqlRuntimeHealth(sessions, uuid4(), VERSIONS)
    await health.register()
    await health.heartbeat(ready=True)
    # Changing a Python object's expectation is not capability registration.
    configured_later = SqlRuntimeHealth(sessions, health.worker_id, VERSIONS, REPORT_GUARD_VERSION)
    await configured_later.heartbeat()
    slot = await read_slot(sessions)
    assert slot.runtime_report_guard_version is None
    assert slot.runtime_heartbeat_at is not None
    assert require_runtime_ready(slot, slot.runtime_heartbeat_at) == VERSIONS
    await health.revoke(clean=True)
    assert (await read_slot(sessions)).runtime_report_guard_version is None


async def test_actual_injected_guard_registers_one_then_retirement_clears_before_old_worker(
    identity_engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    # Import only inside a migrated test, never register extra ORM during collection.
    from studymate.infrastructure.operator.report_triage_guard import SqlReportTriageSourceGuard

    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    guard = SqlReportTriageSourceGuard()
    runtime = create_ai_worker_runtime(
        sessions, Storage(b"synthetic"), configuration(tmp_path), reports=guard
    )
    assert runtime.queue.reports is guard
    assert runtime.health.report_guard_version == REPORT_GUARD_VERSION
    await runtime.health.register()
    assert (await read_slot(sessions)).runtime_report_guard_version == REPORT_GUARD_VERSION
    await runtime.health.heartbeat(ready=True)
    await runtime.health.heartbeat()
    current = await read_slot(sessions)
    assert current.runtime_report_guard_version == REPORT_GUARD_VERSION
    assert current.runtime_heartbeat_at is not None
    assert require_runtime_ready(current, current.runtime_heartbeat_at).model == "synthetic-model"
    await runtime.health.revoke(clean=False)
    assert (await read_slot(sessions)).runtime_state == "blocked"
    await runtime.health.revoke(clean=True)
    retired = await read_slot(sessions)
    assert retired.runtime_state == "stopped"
    assert retired.runtime_worker_id is None
    assert retired.runtime_report_guard_version is None
    replacement = SqlRuntimeHealth(sessions, uuid4(), VERSIONS)
    await replacement.register()
    await replacement.heartbeat(ready=True)
    assert (await read_slot(sessions)).runtime_report_guard_version is None
    await replacement.revoke(clean=True)


@pytest.mark.parametrize("invalid", ["unsupported_version", "stopped_nonnull"])
async def test_database_rejects_unknown_or_stopped_nonnull_guard_capability(
    identity_engine: AsyncEngine,
    invalid: str,
) -> None:
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    health = SqlRuntimeHealth(sessions, uuid4(), VERSIONS)
    if invalid == "unsupported_version":
        await health.register()
        await health.heartbeat(ready=True)
    with pytest.raises(IntegrityError, match="ck_ai_executor_slot_runtime_report_guard"):
        async with sessions.begin() as session:
            await session.execute(
                update(AiSlotRecord)
                .where(AiSlotRecord.id == 1)
                .values(runtime_report_guard_version=2 if invalid == "unsupported_version" else 1)
            )
    assert (await read_slot(sessions)).runtime_report_guard_version is None
    if invalid == "unsupported_version":
        await health.revoke(clean=True)
