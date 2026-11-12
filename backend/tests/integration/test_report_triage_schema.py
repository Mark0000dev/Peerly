"""Exact0060 transition and non-discardable source/runtime capability proof."""

from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.infrastructure.ai.runtime.health import REPORT_GUARD_VERSION, SqlRuntimeHealth
from tests.integration.ai.test_queue import VERSIONS
from tests.integration.migrations import migrate, run_revision_step

pytestmark = pytest.mark.integration
TABLES = {"report_triage_evidence_snapshots", "report_triage_submissions"}


async def test_empty59_to60_roundtrip_has_no_capability_backfill(engine: AsyncEngine) -> None:
    def roundtrip(connection: Connection) -> None:
        migrate(connection, "0059_human_reviews")
        before = set(inspect(connection).get_table_names())
        migrate(connection, "0060_report_triage")
        assert set(inspect(connection).get_table_names()) == before | TABLES
        assert (
            connection.scalar(text("SELECT runtime_report_guard_version FROM ai_executor_slot"))
            is None
        )
        configuration = Config("alembic.ini")
        configuration.attributes["connection"] = connection
        command.downgrade(configuration, "0059_human_reviews")
        assert set(inspect(connection).get_table_names()) == before
        migrate(connection, "0060_report_triage")
        assert set(inspect(connection).get_table_names()) == before | TABLES

    async with engine.begin() as connection:
        await connection.run_sync(roundtrip)


async def test_current_runtime_guard_cannot_be_erased_without_retirement(
    identity_engine: AsyncEngine,
) -> None:
    health = SqlRuntimeHealth(
        async_sessionmaker(identity_engine, expire_on_commit=False),
        uuid4(),
        VERSIONS,
        report_guard_version=REPORT_GUARD_VERSION,
    )
    await health.register()
    try:
        async with identity_engine.begin() as connection:
            with pytest.raises(RuntimeError, match="active guard capability"):
                await connection.run_sync(run_revision_step, "0060_report_triage", "downgrade")
    finally:
        await health.revoke(clean=True)
