from datetime import datetime

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.operator.report_triage import ReadReportTriage
from studymate.domain.ai.tasks import Priority, ReportTriage
from studymate.infrastructure.ai.queue import SqlAiQueue
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
    SessionRecord,
)
from tests.integration.identity_recreation.fixtures import fresh_account, google_claim
from tests.integration.operator.report_triage.fixture import prepared
from tests.integration.operator.report_triage.worker_test import human_review, revoke_grant
from tests.integration.operator.test_reads import operator
from tests.integration.requests.fixture import HASHER

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("changed", ["session", "grant", "ban", "delete", "lineage", "review"])
async def test_current_other_operator_sees_no_advice_after_original_authority_or_source_changes(
    ai_engine: AsyncEngine,
    triage_queue: SqlAiQueue,
    changed: str,
) -> None:
    api = await prepared(ai_engine)
    submitted = await api.enqueue()(await api.command())
    claimed = await triage_queue.claim()
    assert claimed is not None
    await triage_queue.complete(
        claimed, ReportTriage(Priority.HIGH, "Controlled private advisory"), stopped=True
    )
    viewer = await operator(ai_engine)
    if changed == "grant":
        await revoke_grant(api)
    elif changed == "review":
        await human_review(api)
    else:
        historical = await fresh_account(ai_engine) if changed == "lineage" else None
        async with api.unit.sessions.begin() as session:
            at = await session.scalar(select(func.clock_timestamp()))
            assert isinstance(at, datetime)
            if changed == "session":
                await session.execute(
                    update(SessionRecord)
                    .where(SessionRecord.account_id == api.reports.owner.id)
                    .values(revoked_at=at)
                )
            elif changed in {"ban", "delete"}:
                values = {"banned_at" if changed == "ban" else "deleted_at": at}
                await session.execute(
                    update(AccountRecord)
                    .where(AccountRecord.id == api.reports.owner.id)
                    .values(**values)
                )
            else:
                assert historical is not None
                subject = (
                    await session.scalars(
                        select(ExternalIdentityRecord.subject).where(
                            ExternalIdentityRecord.account_id == api.reports.owner.id,
                            ExternalIdentityRecord.retired_at.is_(None),
                        )
                    )
                ).one()
                await session.execute(
                    update(AccountRecord)
                    .where(AccountRecord.id == historical)
                    .values(deleted_at=at, banned_at=at)
                )
                retained = google_claim(historical, subject, at)
                retained.retired_at = at
                session.add(retained)
    current = await ReadReportTriage(api.unit, HASHER)(viewer.credential, api.reports.report.id)
    assert current is not None
    assert current.triage is not None
    assert current.triage.observation.job_id == submitted.observation.job_id
    assert current.triage.observation.source_current is False
    assert current.triage.observation.priority is None
    assert current.triage.observation.rationale is None
