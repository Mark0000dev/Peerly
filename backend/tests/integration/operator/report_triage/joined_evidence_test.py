import asyncio
import json
from dataclasses import replace
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from studymate.application.idempotency import IntentKey
from studymate.application.operator.authority import require_operator
from studymate.application.operator.report_triage import ReadReportTriageContext
from studymate.application.report_moderation.review import ReviewReport, ReviewReportCommand
from studymate.domain.report_moderation.reviews import (
    ReportReviewAction,
    ReportReviewReason,
    ReportReviewRevision,
)
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.operator.report_triage_sources import (
    selected_locked_report_preview as selected_report_preview,
)
from studymate.infrastructure.operator.report_triage_transactions import (
    SqlOperatorReportTriageUnitOfWork,
)
from studymate.infrastructure.persistence.product_events import (
    record_operator_audit,
    record_report_review_event,
    record_report_triage_submission,
)
from studymate.infrastructure.persistence.profile_models import ProfileRecord, ProfileRevisionRecord
from studymate.infrastructure.report_moderation.transactions import (
    SqlReportModerationUnitOfWork,
    report_source,
)
from tests.integration.operator.report_triage.fixture import CODEC, prepared
from tests.integration.operator.test_reads import operator
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.safety.message_reports.fixture import prepared as image_report

pytestmark = pytest.mark.integration


async def test_joined_profile_evidence_uses_one_query_and_original_selected_revision(
    ai_engine: AsyncEngine,
) -> None:
    api = await prepared(ai_engine)
    async with api.unit.sessions.begin() as session:
        profile = await session.get(ProfileRecord, api.reports.target.id)
        assert profile is not None
        old = await session.get(
            ProfileRevisionRecord, (profile.account_id, profile.current_version)
        )
        assert old is not None
        original = old.display_name, old.about, old.version
        at = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(at, datetime)
        session.add(
            ProfileRevisionRecord(
                account_id=profile.account_id,
                version=profile.current_version + 1,
                display_name="Changed current display",
                about="Changed current private about",
                task=old.task,
                saved_at=at,
            )
        )
        await session.flush()
        await session.execute(
            update(ProfileRecord)
            .where(ProfileRecord.account_id == profile.account_id)
            .values(current_version=profile.current_version + 1)
        )
    observed: list[str] = []

    def observe(*arguments: object) -> None:
        statement = arguments[2]
        if isinstance(statement, str):
            observed.append(statement.split(maxsplit=1)[0])

    digest = await HASHER.digest(api.reports.owner.credential)
    async with api.unit.transaction(digest, api.reports.report.id) as transaction:
        await require_operator(transaction, api.reports.owner.credential, HASHER)
        source = await report_source(transaction.session, api.reports.report.id, lock=True)
        assert source is not None
        event.listen(ai_engine.sync_engine, "before_cursor_execute", observe)
        try:
            preview = await selected_report_preview(transaction.session, source)
        finally:
            event.remove(ai_engine.sync_engine, "before_cursor_execute", observe)
        assert observed == ["SELECT"]
        assert preview.context is not None
        evidence = json.loads(preview.context.evidence)
        selected = evidence["selected_item"]
        assert (
            selected["display_name"],
            selected["about"],
            selected["profile_version"],
        ) == original
        assert "Changed current private about" not in preview.context.evidence
        assert preview.context.review_version is None


@pytest.mark.parametrize("field", ["target_id", "context_id"])
async def test_joined_source_mismatch_fails_without_private_read_audit(
    ai_engine: AsyncEngine,
    field: str,
) -> None:
    api = await prepared(ai_engine)
    digest = await HASHER.digest(api.reports.owner.credential)
    async with api.unit.transaction(digest, api.reports.report.id) as transaction:
        await require_operator(transaction, api.reports.owner.credential, HASHER)
        source = await report_source(transaction.session, api.reports.report.id, lock=True)
        assert source is not None
        changed = (
            replace(source, target_id=uuid4())
            if field == "target_id"
            else replace(source, context_id=uuid4())
        )
        with pytest.raises(RuntimeError, match="differs from actual locked report/evidence"):
            await selected_report_preview(transaction.session, changed)
    async with api.unit.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(OperatorAuditRecord)) == 0


async def test_concurrent_human_review_serializes_and_joined_preview_reads_current_version(
    ai_engine: AsyncEngine,
) -> None:
    api = await prepared(ai_engine)
    entered, release, reader_started = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def hold_review(session: AsyncSession, source: ReportReviewRevision) -> None:
        await record_report_review_event(session, source)
        entered.set()
        await release.wait()

    writer = asyncio.create_task(
        ReviewReport(
            SqlReportModerationUnitOfWork(api.unit.sessions, record_operator_audit, hold_review),
            HASHER,
            FINGERPRINTER,
        )(
            ReviewReportCommand(
                api.reports.owner.credential,
                api.reports.report.id,
                0,
                ReportReviewAction.ESCALATE,
                ReportReviewReason("Controlled retained decision"),
                IntentKey("joined-review-race"),
            )
        )
    )

    def observe(*arguments: object) -> None:
        statement = arguments[2]
        if (
            isinstance(statement, str)
            and "FROM accounts" in statement
            and "FOR NO KEY UPDATE" in statement
        ):
            reader_started.set()

    try:
        await asyncio.wait_for(entered.wait(), 1)
        event.listen(ai_engine.sync_engine, "before_cursor_execute", observe)
        reader = asyncio.create_task(
            ReadReportTriageContext(api.unit, HASHER, CODEC)(
                api.reports.owner.credential, api.reports.report.id
            )
        )
        try:
            await asyncio.wait_for(reader_started.wait(), 1)
            assert not reader.done()
            release.set()
            await writer
            result = await reader
            assert result is not None
            assert result.preview.context is not None
            assert result.preview.context.review_version == 1
            assert result.source_token is not None
        finally:
            event.remove(ai_engine.sync_engine, "before_cursor_execute", observe)
            if not reader.done():
                reader.cancel()
                await asyncio.gather(reader, return_exceptions=True)
    finally:
        release.set()
        if not writer.done():
            writer.cancel()
            await asyncio.gather(writer, return_exceptions=True)


async def test_joined_selected_image_uses_one_projection_without_other_chat_content(
    ai_engine: AsyncEngine,
) -> None:
    api = await image_report(ai_engine)
    report = await api.submit()(api.command())
    viewer = await operator(ai_engine)
    unit = SqlOperatorReportTriageUnitOfWork(
        api.uow.sessions, record_operator_audit, record_report_triage_submission
    )
    joined: list[str] = []

    def observe(*arguments: object) -> None:
        statement = arguments[2]
        if (
            isinstance(statement, str)
            and "FROM profile_reports" in statement
            and "LEFT OUTER JOIN profile_revisions" in statement
        ):
            joined.append("selected_projection")

    event.listen(ai_engine.sync_engine, "before_cursor_execute", observe)
    try:
        preview = await ReadReportTriageContext(unit, HASHER, CODEC)(viewer.credential, report.id)
    finally:
        event.remove(ai_engine.sync_engine, "before_cursor_execute", observe)
    assert joined == ["selected_projection"]
    assert preview is not None
    assert preview.preview.context is not None
    evidence = json.loads(preview.preview.context.evidence)
    assert evidence["selected_item"]["message_text"] == "Private image caption"
    assert evidence["selected_item"]["image_pixels_included"] is False
    assert "conversation_history" not in preview.preview.context.evidence
