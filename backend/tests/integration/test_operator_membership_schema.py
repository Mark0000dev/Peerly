"""The exact58 transition and preservation of committed manual membership facts."""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.integration.migrations import migrate, run_revision_step
from tests.integration.operator.membership_verification_test import prepared

pytestmark = pytest.mark.integration

TABLES = {"operator_membership_verifications", "operator_membership_verification_intents"}


async def test_empty57_to58_roundtrip_keeps_existing_schema_and_sources(
    engine: AsyncEngine,
) -> None:
    def roundtrip(connection: Connection) -> None:
        migrate(connection, "0057_operator_audit_search")
        before = set(inspect(connection).get_table_names())
        migrate(connection, "0058_manual_membership")
        assert set(inspect(connection).get_table_names()) == before | TABLES
        configuration = Config("alembic.ini")
        configuration.attributes["connection"] = connection
        command.downgrade(configuration, "0057_operator_audit_search")
        assert set(inspect(connection).get_table_names()) == before
        migrate(connection, "0058_manual_membership")
        assert set(inspect(connection).get_table_names()) == before | TABLES

    async with engine.begin() as connection:
        await connection.run_sync(roundtrip)


async def test_retained_manual_source_refuses_downgrade(identity_engine: AsyncEngine) -> None:
    scenario = await prepared(identity_engine)
    await scenario.verify()(scenario.command)
    async with identity_engine.begin() as connection:
        with pytest.raises(RuntimeError, match="retained manual membership verification facts"):
            await connection.run_sync(run_revision_step, "0058_manual_membership", "downgrade")
