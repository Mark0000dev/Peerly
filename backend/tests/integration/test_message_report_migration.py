"""Real old-profile upgrade and retained image-evidence downgrade protection."""

from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, insert, select
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.infrastructure.persistence.base import Base
from studymate.infrastructure.persistence.message_report_models import MessageReportContextRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.report_models import ProfileReportRecord
from tests.integration.migrations import migrate, run_revision_step
from tests.integration.safety.message_reports.fixture import prepared as image_context

pytestmark = pytest.mark.integration


def downgrade49(connection: Connection) -> None:
    config = Config("alembic.ini")
    config.attributes["connection"] = connection
    command.downgrade(config, "0048_chat_image_cleanup")


async def historical_profile_context(session: AsyncSession) -> tuple[UUID, UUID]:
    """Seed only real head48 columns/constraints, not current application writers."""
    viewer, target, context, upload, attempt = (uuid4() for _ in range(5))
    at = await session.scalar(select(func.clock_timestamp()))
    assert isinstance(at, datetime)
    await session.execute(
        insert(Base.metadata.tables["accounts"]),
        [{"id": viewer, "created_at": at}, {"id": target, "created_at": at}],
    )
    await session.execute(
        insert(Base.metadata.tables["profile_revisions"]).values(
            account_id=target,
            version=1,
            display_name="Synthetic historical profile",
            task="find_help",
            saved_at=at,
        )
    )
    await session.execute(
        insert(Base.metadata.tables["profiles"]).values(account_id=target, current_version=1)
    )
    await session.execute(
        insert(Base.metadata.tables["photo_uploads"]).values(
            id=upload,
            account_id=target,
            current_version=4,
            expected_photo_version=0,
            source_size=1,
            source_digest=b"x" * 32,
            content_type="image/png",
            created_at=at,
            upload_expires_at=at + timedelta(minutes=1),
            processing_expires_at=at + timedelta(minutes=2),
        )
    )
    await session.execute(
        insert(Base.metadata.tables["photo_processing_attempts"]).values(
            id=attempt,
            upload_id=upload,
            number=1,
            started_at=at,
            lease_until=at + timedelta(minutes=1),
            finished_at=at,
            outcome="ready",
            display_width=1,
            display_height=1,
            display_size=1,
            display_digest=b"y" * 32,
        )
    )
    await session.execute(
        insert(Base.metadata.tables["photo_upload_revisions"]),
        [
            {
                "upload_id": upload,
                "account_id": target,
                "version": version,
                "state": state,
                "updated_at": at,
                "attempt_id": attempt if state in ("processing", "ready") else None,
            }
            for version, state in enumerate(("uploading", "queued", "processing", "ready"), start=1)
        ],
    )
    await session.execute(
        insert(Base.metadata.tables["photo_revisions"]).values(
            account_id=target,
            version=1,
            upload_id=upload,
            upload_version=4,
            upload_state="ready",
            saved_at=at,
        )
    )
    await session.execute(
        insert(Base.metadata.tables["photos"]).values(account_id=target, current_version=1)
    )
    await session.execute(
        insert(Base.metadata.tables["profile_access_contexts"]).values(
            id=context,
            viewer_id=viewer,
            target_id=target,
            profile_version=1,
            photo_version=1,
            issued_at=at,
        )
    )
    return viewer, context


async def test_existing_profile_report_is_classified_from_real_old_shape_without_new_events(
    engine: AsyncEngine,
) -> None:
    # Direct old-schema source fixture. Current application canonical event writers
    # are intentionally never called before the real upgrade to head.
    async with engine.begin() as connection:
        await connection.run_sync(migrate, "0048_chat_image_cleanup")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    report_id = uuid4()
    async with sessions.begin() as session:
        viewer_id, context_id = await historical_profile_context(session)
        # Explicit historical columns: the current mapper has additive49 fields.
        await session.execute(
            insert(Base.metadata.tables["profile_reports"]).values(
                id=report_id,
                reporter_id=viewer_id,
                context_id=context_id,
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
        assert report.context_id == context_id
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
        assert retained.context_id == context_id
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
            await connection.run_sync(run_revision_step, "0049_message_image_reports", "downgrade")
    with pytest.raises(RuntimeError, match="retained observations or external delivery facts"):
        async with identity_engine.begin() as connection:
            await connection.run_sync(downgrade49)
    async with source.chat.api.sessions() as session:
        assert await session.get(MessageReportContextRecord, source.context.id) is not None
        if report is not None:
            assert await session.get(ProfileReportRecord, report.id) is not None
