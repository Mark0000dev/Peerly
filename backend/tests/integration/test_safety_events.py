from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

import studymate.infrastructure.persistence.product_events as events_module
from studymate.application.idempotency import IntentKey
from studymate.application.safety.blocks import ChangeBlockCommand, ChangeOwnBlock
from studymate.application.safety.profile_reports import (
    SubmitProfileReport,
    SubmitProfileReportCommand,
)
from studymate.domain.reports import ReportCategory
from studymate.infrastructure.observability.origin import ExecutionOrigin
from studymate.infrastructure.persistence.blocks import SqlBlockUnitOfWork
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.profile_reports import SqlProfileReportUnitOfWork
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.safety_fixture import prepared

pytestmark = pytest.mark.integration


async def test_safety_outcomes_are_atomic_once_only_and_content_free(
    identity_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    viewer, target, context = await prepared(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    hasher = Sha256SessionHasher()
    fingerprinter = HmacIntentFingerprinter(bytes(range(32)))
    change = ChangeOwnBlock(SqlBlockUnitOfWork(sessions), hasher, fingerprinter)
    report = SubmitProfileReport(SqlProfileReportUnitOfWork(sessions), hasher, fingerprinter)
    origin = ExecutionOrigin(uuid4(), uuid4(), "a" * 32, "b" * 16)
    monkeypatch.setattr(events_module, "current_origin", lambda: origin)
    block = ChangeBlockCommand(
        viewer.credential, target.id, True, 0, IntentKey(str(uuid4())), context.id
    )
    await change(block)
    await change(block)
    await change(replace(block, expected_version=1, intent_key=IntentKey(str(uuid4()))))
    await change(
        replace(block, blocked=False, expected_version=1, intent_key=IntentKey(str(uuid4())))
    )
    submission = SubmitProfileReportCommand(
        viewer.credential,
        context.id,
        ReportCategory.OTHER,
        IntentKey(str(uuid4())),
        "Private evidence must stay in the business report",
    )
    saved = await report(submission)
    assert await report(submission) == saved
    async with sessions() as session:
        events = tuple(
            await session.scalars(
                select(ProductEventRecord)
                .where(ProductEventRecord.kind.in_(("report.created", "block.changed")))
                .order_by(ProductEventRecord.occurred_at)
            )
        )
        assert tuple(row.kind for row in events) == (
            "block.changed",
            "block.changed",
            "report.created",
        )
        assert tuple(row.blocked for row in events) == (True, False, None)
        assert events[-1].report_id == saved.id
        assert all(row.account_id == viewer.id for row in events)
        assert all(row.request_id == origin.request_id for row in events)
        assert all(row.action_id == origin.action_id for row in events)
        assert all(
            row.trace_id == origin.trace_id and row.span_id == origin.span_id for row in events
        )
        assert "comment" not in ProductEventRecord.__table__.columns
        relationship_id = events[0].block_relationship_id
    with pytest.raises(IntegrityError):
        async with sessions.begin() as session:
            session.add(
                ProductEventRecord(
                    id=uuid4(),
                    account_id=target.id,
                    kind="report.created",
                    occurrence_key="forged:report",
                    schema_version=1,
                    occurred_at=datetime.now(UTC),
                    report_id=saved.id,
                )
            )
    with pytest.raises(IntegrityError):
        async with sessions.begin() as session:
            session.add(
                ProductEventRecord(
                    id=uuid4(),
                    account_id=viewer.id,
                    kind="block.changed",
                    occurrence_key="forged:block",
                    schema_version=1,
                    occurred_at=datetime.now(UTC),
                    block_relationship_id=relationship_id,
                    block_version=1,
                    blocked=False,
                )
            )
