from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import DateTime, cast, func, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.integration.catalogue_fixture import subject
from tests.integration.migrations import migrate
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration


def downgrade(connection: Connection) -> None:
    config = Config("alembic.ini")
    config.attributes["connection"] = connection
    command.downgrade(config, "0028_request_events")


async def test_topic_key_upgrade_backfills_unicode_without_revising_source_history(
    engine: AsyncEngine,
) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(migrate, "0028_request_events")
    owner = await actor(engine)
    known = await subject(engine)
    goal_id = uuid4()
    async with engine.begin() as connection:
        now = (
            await connection.execute(select(cast(func.clock_timestamp(), DateTime(timezone=True))))
        ).scalar_one()
        await connection.execute(
            text(
                "INSERT INTO goals (id,account_id,current_version,created_at) VALUES (:id"
                ",:owner,1,:at)"
            ),
            {"id": goal_id, "owner": owner.id, "at": now},
        )
        await connection.execute(
            text(
                "INSERT INTO goal_revisions (goal_id,account_id,version,subject_id,subjec"
                "t_label,topic,shared_learning,saved_at) VALUES (:id,:owner,1,:subject,:l"
                "abel,:topic,false,:at)"
            ),
            {
                "id": goal_id,
                "owner": owner.id,
                "subject": known.id,
                "label": known.name,
                "topic": "Straße JOINs",
                "at": now,
            },
        )
        await connection.execute(
            text("INSERT INTO help_revisions (account_id,version,saved_at) VALUES (:owner,1,:at)"),
            {"owner": owner.id, "at": now},
        )
        await connection.execute(
            text(
                "INSERT INTO help_selections (account_id,version,slot,subject_id,subject_"
                "label,topic_note) VALUES (:owner,1,0,:subject,:label,:topic)"
            ),
            {
                "owner": owner.id,
                "subject": known.id,
                "label": known.name,
                "topic": "STRASSE   joins",
            },
        )
    for repeat in (False, True):
        async with engine.begin() as connection:
            if repeat:
                await connection.run_sync(downgrade)
            await connection.run_sync(migrate, "head")
            goal = (
                await connection.execute(text("SELECT topic,topic_match_key FROM goal_revisions"))
            ).one()
            helper = (
                await connection.execute(
                    text("SELECT topic_note,topic_match_key FROM help_selections")
                )
            ).one()
            assert goal == ("Straße JOINs", "strasse joins")
            assert helper == ("STRASSE   joins", "strasse joins")
            assert (
                await connection.execute(text("SELECT count(*) FROM goal_revisions"))
            ).scalar_one() == 1
            assert (
                await connection.execute(text("SELECT count(*) FROM product_events"))
            ).scalar_one() == 0
