from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, inspect, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.infrastructure.ai.models import AiSlotRecord
from tests.integration.migrations import migrate, run_revision_step

pytestmark = pytest.mark.integration


async def test_existing_executor_capacity_is_not_enabled_by_runtime_upgrade(
    engine: AsyncEngine,
) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(migrate, "0050_bootstrap_catalogue")
        before = (await connection.execute(text("SELECT * FROM ai_executor_slot"))).mappings().one()
        await connection.run_sync(migrate, "0051_ai_runtime_health")
        after = (await connection.execute(text("SELECT * FROM ai_executor_slot"))).mappings().one()
        assert all(after[key] == value for key, value in before.items())
        assert after["runtime_state"] == "stopped"
        assert after["runtime_worker_id"] is None
        assert after["runtime_valid_until"] is None
        await connection.run_sync(run_revision_step, "0051_ai_runtime_health", "downgrade")
        columns = await connection.run_sync(
            lambda sync: {
                column["name"] for column in inspect(sync).get_columns("ai_executor_slot")
            }
        )
        assert "runtime_worker_id" not in columns


async def test_runtime_cannot_claim_ready_without_bound_freshness_and_versions(
    identity_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await session.execute(update(AiSlotRecord).values(runtime_state="ready"))
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        values = {
            "runtime_state": "ready",
            "runtime_worker_id": uuid4(),
            "runtime_started_at": now,
            "runtime_heartbeat_at": now,
            "runtime_valid_until": now + timedelta(seconds=15),
            "runtime_model": "synthetic-model",
            "runtime_prompt": "synthetic-prompt",
            "runtime_schema": "synthetic-schema",
            "runtime_adapter": "synthetic-adapter",
        }
        await session.execute(update(AiSlotRecord).values(**values))
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await session.execute(
                    update(AiSlotRecord).values(runtime_valid_until=now + timedelta(days=1))
                )
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await session.execute(update(AiSlotRecord).values(runtime_adapter=" "))


async def test_runtime_downgrade_refuses_active_owner_without_releasing_slot(
    identity_engine: AsyncEngine,
) -> None:
    async with identity_engine.begin() as connection:
        now = (await connection.execute(select(func.clock_timestamp()))).scalar_one()
        assert isinstance(now, datetime)
        worker = uuid4()
        await connection.execute(
            update(AiSlotRecord).values(
                runtime_state="blocked",
                runtime_worker_id=worker,
                runtime_started_at=now,
                runtime_heartbeat_at=now,
                runtime_valid_until=now + timedelta(seconds=15),
                runtime_model="synthetic",
                runtime_prompt="synthetic",
                runtime_schema="synthetic",
                runtime_adapter="synthetic",
            )
        )
        with pytest.raises(RuntimeError, match="Stop and confirm"):
            await connection.run_sync(run_revision_step, "0051_ai_runtime_health", "downgrade")
        row = (
            await connection.execute(
                select(AiSlotRecord.runtime_worker_id, AiSlotRecord.runtime_state)
            )
        ).one()
        assert row == (worker, "blocked")
