from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.ai.ports import AiUnavailableError
from studymate.infrastructure.ai.models import AiJobRecord
from studymate.infrastructure.ai.runtime.health import SqlRuntimeHealth
from studymate.infrastructure.operator.report_triage_models import (
    ReportTriageEvidenceRecord,
    ReportTriageSubmissionRecord,
)
from tests.integration.ai.test_queue import VERSIONS
from tests.integration.operator.report_triage.fixture import prepared

pytestmark = pytest.mark.integration


async def test_fresh_ready_worker_without_actual_report_guard_cannot_admit_internal_triage(
    identity_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    # Default registration represents the existing student-only worker. Readiness
    # and native versions alone do not prove internal report-source validation.
    health = SqlRuntimeHealth(sessions, uuid4(), VERSIONS)
    await health.register()
    await health.heartbeat(ready=True)
    try:
        api = await prepared(identity_engine)
        request = await api.command()
        with pytest.raises(AiUnavailableError):
            await api.enqueue()(request)
        async with sessions() as session:
            assert tuple(await session.scalars(select(AiJobRecord))) == ()
            assert tuple(await session.scalars(select(ReportTriageEvidenceRecord))) == ()
            assert tuple(await session.scalars(select(ReportTriageSubmissionRecord))) == ()
    finally:
        await health.revoke(clean=True)
