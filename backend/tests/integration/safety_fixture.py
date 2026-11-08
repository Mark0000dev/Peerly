"""Actual activated profiles and an explicit retained disclosure test fixture."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.domain.reports import ProfileAccessContext
from studymate.infrastructure.persistence.goal_models import GoalRecord
from studymate.infrastructure.persistence.profile_reports import access_context_value
from studymate.infrastructure.persistence.report_models import ProfileAccessRecord
from tests.integration.onboarding_fixture import ready_setup
from tests.integration.profile_lifecycle_fixture import activated, complete_existing_setup
from tests.integration.student_actor import Actor, actor


async def prepared(engine: AsyncEngine) -> tuple[Actor, Actor, ProfileAccessContext]:
    viewer = await activated(engine)
    target = await actor(engine)
    await ready_setup(engine, target.credential)
    await complete_existing_setup(engine, target)
    async with async_sessionmaker(engine, expire_on_commit=False).begin() as session:
        goal = await session.scalar(select(GoalRecord).where(GoalRecord.account_id == target.id))
        assert goal is not None
        context = ProfileAccessRecord(
            id=uuid4(),
            viewer_id=viewer.id,
            target_id=target.id,
            profile_version=1,
            photo_version=1,
            goal_id=goal.id,
            goal_version=goal.current_version,
            help_version=None,
            issued_at=datetime.now(UTC),
        )
        session.add(context)
        result = access_context_value(context)
    return viewer, target, result
