"""Actual canonical Alembic transitions, not metadata create_all or offline DDL."""

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.infrastructure.persistence.identity_models import SessionRecord
from tests.integration.migrations import migrate
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration
HEAD = "0064_notification_subscriptions"


def constraints(connection: Connection) -> None:
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    required = {
        "student_notification_subscriptions",
        "student_notification_subscription_intents",
        "student_notification_device_attempts",
    }
    assert required <= tables
    foreign = inspector.get_foreign_keys("student_notification_subscriptions")
    assert any(
        row["constrained_columns"] == ["enrolled_session_id", "account_id"]
        and row["referred_table"] == "sessions"
        and row["referred_columns"] == ["id", "account_id"]
        for row in foreign
    )
    unique = inspector.get_unique_constraints("student_notification_deliveries")
    assert any(
        row["name"] == "uq_student_notification_owned_delivery"
        and row["column_names"] == ["id", "recipient_id"]
        for row in unique
    )


@pytest.mark.parametrize("predecessor", ["base", "0060_report_triage", "0062_google_display"])
async def test_actual_empty_or_0062_upgrades_to_0064(engine: AsyncEngine, predecessor: str) -> None:
    retained = None
    if predecessor != "base":
        async with engine.begin() as connection:
            await connection.run_sync(migrate, predecessor)
        retained = await actor(engine)
    async with engine.begin() as connection:
        await connection.run_sync(migrate, "head")
        assert (
            await connection.execute(text("SELECT version_num FROM alembic_version"))
        ).scalar_one() == HEAD
        await connection.run_sync(constraints)
    if retained is not None:
        async with async_sessionmaker(engine)() as session:
            assert (
                await session.scalar(
                    select(SessionRecord.id).where(SessionRecord.account_id == retained.id)
                )
                is not None
            )
