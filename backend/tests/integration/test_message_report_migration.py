"""Real old-profile upgrade and retained image-evidence downgrade protection."""

from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, insert, select
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.infrastructure.persistence.message_report_models import MessageReportContextRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.report_models import ProfileReportRecord
from tests.integration.migrations import migrate
from tests.integration.safety.message_reports.fixture import prepared as image_context
from tests.integration.safety_fixture import prepared as profile_context

pytestmark = pytest.mark.integration


def downgrade49(connection: Connection) -> None:
    config = Config("alembic.ini")
    config.attributes["connection"] = connection
    command.downgrade(config, "0048_chat_image_cleanup")


async def test_existing_profile_report_is_classified_from_real_old_shape_without_new_events(
    engine: AsyncEngine,
) -> None:
    # The current application writes current canonical columns. Materialize genuine
    # source context first, then return it to the actual old schema before inserting
    # the historical report; never execute the head52 mapper against head48 tables.
    async with engine.begin() as connection:
        await connection.run_sync(migrate, "head")
    viewer, _, context = await profile_context(engine)
    async with engine.begin() as connection:
        await connection.run_sync(downgrade49)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    report_id = uuid4()
    async with sessions.begin() as session:
        # Explicit historical columns: the current mapped class has additive49 fields.
        # This is an old-source fixture, not a fabricated migration business outcome.
        await session.execute(
            insert(ProfileReportRecord).values(
                id=report_id,
                reporter_id=viewer.id,
                context_id=context.id,
                category="spam",
                comment="Retained old private report",
                submitted_at=func.clock_timestamp(),
            )
        )
    async with engine.begin() as connection:
        await connection.run_sync(migrate, "head")
    async with sessions() as session:
        report = await session.get(ProfileReportRecord, report_id)
        assert report is not None
        assert report.kind == "profile"
        assert report.context_id == context.id
        assert report.message_context_id is None
        assert report.comment == "Retained old private report"
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProductEventRecord)
                .where(ProductEventRecord.report_id == report_id)
            )
            == 0
        )
    async with engine.begin() as connection:
        await connection.run_sync(downgrade49)
        await connection.run_sync(migrate, "head")
    async with sessions() as session:
        retained = await session.get(ProfileReportRecord, report_id)
        assert retained is not None
        assert retained.kind == "profile"
        assert retained.context_id == context.id
        assert retained.comment == "Retained old private report"


@pytest.mark.parametrize("submitted", [False, True])
async def test_real_downgrade_refuses_to_drop_retained_image_evidence(
    identity_engine: AsyncEngine,
    submitted: bool,
) -> None:
    source = await image_context(identity_engine)
    report = await source.submit()(source.command()) if submitted else None
    with pytest.raises(RuntimeError, match="retained message image report evidence"):
        async with identity_engine.begin() as connection:
            await connection.run_sync(downgrade49)
    async with source.chat.api.sessions() as session:
        assert await session.get(MessageReportContextRecord, source.context.id) is not None
        if report is not None:
            assert await session.get(ProfileReportRecord, report.id) is not None
