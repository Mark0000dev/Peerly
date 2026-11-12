"""Exact0059 transition, retained proof guard and frozen model/CHECK contract."""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.integration.migrations import migrate, run_revision_step
from tests.integration.operator.test_photo_review import request_replacement
from tests.integration.operator.test_reads import operator
from tests.integration.profile_lifecycle_fixture import activated

pytestmark = pytest.mark.integration
TABLES = {
    "operator_photo_review_revisions",
    "operator_photo_review_intents",
    "operator_report_review_revisions",
    "operator_report_review_intents",
}


async def test_empty58_to59_roundtrip_preserves_existing_sources(engine: AsyncEngine) -> None:
    def roundtrip(connection: Connection) -> None:
        migrate(connection, "0058_manual_membership")
        before = set(inspect(connection).get_table_names())
        migrate(connection, "0059_human_reviews")
        assert set(inspect(connection).get_table_names()) == before | TABLES
        configuration = Config("alembic.ini")
        configuration.attributes["connection"] = connection
        command.downgrade(configuration, "0058_manual_membership")
        assert set(inspect(connection).get_table_names()) == before
        migrate(connection, "0059_human_reviews")
        assert set(inspect(connection).get_table_names()) == before | TABLES

    async with engine.begin() as connection:
        await connection.run_sync(roundtrip)


async def test_human_source_cannot_be_discarded_by_downgrade(identity_engine: AsyncEngine) -> None:
    target, viewer = await activated(identity_engine), await operator(identity_engine)
    await request_replacement(identity_engine, viewer, target)
    async with identity_engine.begin() as connection:
        with pytest.raises(RuntimeError, match="Refusing to remove retained human review evidence"):
            await connection.run_sync(run_revision_step, "0059_human_reviews", "downgrade")
