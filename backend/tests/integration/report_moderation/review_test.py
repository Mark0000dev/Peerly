import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from studymate.application.idempotency import IntentKey
from studymate.application.report_moderation.history import ReadReportReviewHistory
from studymate.application.report_moderation.review import (
    ReportReviewVersionConflictError,
    ReviewReport,
    ReviewReportCommand,
)
from studymate.domain.report_moderation.reviews import (
    REVIEW_HISTORY_PAGE_SIZE,
    ReportReviewAction,
    ReportReviewReason,
    ReportReviewRevision,
)
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import (
    record_operator_audit,
    record_report_review_event,
)
from studymate.infrastructure.report_moderation.cursors import FernetReportReviewHistoryCursorCodec
from studymate.infrastructure.report_moderation.models import (
    ReportReviewIntentRecord,
    ReportReviewRevisionRecord,
)
from studymate.infrastructure.report_moderation.transactions import SqlReportModerationUnitOfWork
from tests.integration.operator.test_reads import operator
from tests.integration.operator.test_reports import reports
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.safety.message_reports.fixture import prepared as message_report

pytestmark = pytest.mark.integration
CODEC = FernetReportReviewHistoryCursorCodec.from_key(b"r" * 32)


async def test_actual_human_proof_exact_replay_and_deleted_subject_retention(
    identity_engine: AsyncEngine,
) -> None:
    api = await reports(identity_engine)
    unit = SqlReportModerationUnitOfWork(
        api.uow.sessions, record_operator_audit, record_report_review_event
    )
    command = ReviewReportCommand(
        api.owner.credential,
        api.report.id,
        0,
        ReportReviewAction.DISMISS,
        ReportReviewReason("  exact private human decision  "),
        IntentKey("human-review-proof"),
    )
    async with api.uow.sessions.begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == api.target.id)
            .values(deleted_at=func.clock_timestamp(), banned_at=func.clock_timestamp())
        )
    write = ReviewReport(unit, HASHER, FINGERPRINTER)
    original = await write(command)
    assert await write(command) == original
    async with api.uow.sessions() as session:
        source = (await session.scalars(select(ReportReviewRevisionRecord))).one()
        assert source.operator_id == api.owner.id
        assert source.actor_session_id == original.actor_session_id
        assert source.reason == command.reason.value
        event = await session.get(ProductEventRecord, original.event_id)
        assert event is not None
        assert event.kind == "report.reviewed"
        assert event.account_id == api.owner.id
        assert event.occurrence_key == original.occurrence_key
        assert event.occurred_at == original.reviewed_at
        target = await session.get(AccountRecord, api.target.id)
        assert target is not None
        assert target.deleted_at is not None
        assert target.banned_at is not None
        assert tuple(await session.scalars(select(OperatorAuditRecord))) == ()
    history = await ReadReportReviewHistory(unit, HASHER, CODEC)(
        api.owner.credential, api.report.id
    )
    assert history is not None
    assert history.current == original
    assert history.report.target_id == api.target.id


async def test_different_humans_racing_same_expected_version_commit_one_decision(
    identity_engine: AsyncEngine,
) -> None:
    api = await reports(identity_engine)
    second = await operator(identity_engine)
    unit = SqlReportModerationUnitOfWork(
        api.uow.sessions, record_operator_audit, record_report_review_event
    )
    write = ReviewReport(unit, HASHER, FINGERPRINTER)
    first = ReviewReportCommand(
        api.owner.credential,
        api.report.id,
        0,
        ReportReviewAction.DISMISS,
        ReportReviewReason("first human decision"),
        IntentKey("racing-review-first"),
    )
    other = replace(
        first,
        credential=second.credential,
        action=ReportReviewAction.ESCALATE,
        intent_key=IntentKey("racing-review-other"),
    )
    results = await asyncio.gather(write(first), write(other), return_exceptions=True)
    assert sum(isinstance(result, ReportReviewRevision) for result in results) == 1
    assert sum(isinstance(result, ReportReviewVersionConflictError) for result in results) == 1
    async with api.uow.sessions() as session:
        assert len(tuple(await session.scalars(select(ReportReviewRevisionRecord)))) == 1
        assert len(tuple(await session.scalars(select(ReportReviewIntentRecord)))) == 1


async def test_concurrent_same_actor_key_replays_one_original_source(
    identity_engine: AsyncEngine,
) -> None:
    api = await reports(identity_engine)
    unit = SqlReportModerationUnitOfWork(
        api.uow.sessions, record_operator_audit, record_report_review_event
    )
    write = ReviewReport(unit, HASHER, FINGERPRINTER)
    command = ReviewReportCommand(
        api.owner.credential,
        api.report.id,
        0,
        ReportReviewAction.ESCALATE,
        ReportReviewReason("requires human escalation"),
        IntentKey("concurrent-review"),
    )
    first, second = await asyncio.gather(write(command), write(command))
    assert first == second
    async with api.uow.sessions() as session:
        assert len(tuple(await session.scalars(select(ReportReviewRevisionRecord)))) == 1
        events = tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "report.reviewed")
            )
        )
        assert tuple(event.id for event in events) == (first.event_id,)


async def fail_canonical(session: AsyncSession, source: ReportReviewRevision) -> None:
    await record_report_review_event(session, source)
    raise RuntimeError("synthetic report canonical failure")


async def test_actual_canonical_failure_rolls_back_review_intent_and_event(
    identity_engine: AsyncEngine,
) -> None:
    api = await reports(identity_engine)
    unit = SqlReportModerationUnitOfWork(api.uow.sessions, record_operator_audit, fail_canonical)
    write = ReviewReport(unit, HASHER, FINGERPRINTER)
    command = ReviewReportCommand(
        api.owner.credential,
        api.report.id,
        0,
        ReportReviewAction.DISMISS,
        ReportReviewReason("human reason"),
        IntentKey("rollback-review"),
    )
    with pytest.raises(RuntimeError, match="synthetic report canonical failure"):
        await write(command)
    async with api.uow.sessions() as session:
        assert tuple(await session.scalars(select(ReportReviewRevisionRecord))) == ()
        assert tuple(await session.scalars(select(ReportReviewIntentRecord))) == ()
        assert (
            tuple(
                await session.scalars(
                    select(ProductEventRecord).where(ProductEventRecord.kind == "report.reviewed")
                )
            )
            == ()
        )


async def test_message_image_report_keeps_actual_evidence_kind_and_owner(
    identity_engine: AsyncEngine,
) -> None:
    api = await message_report(identity_engine)
    report = await api.submit()(api.command())
    viewer = await operator(identity_engine)
    unit = SqlReportModerationUnitOfWork(
        api.uow.sessions, record_operator_audit, record_report_review_event
    )
    result = await ReviewReport(unit, HASHER, FINGERPRINTER)(
        ReviewReportCommand(
            viewer.credential,
            report.id,
            0,
            ReportReviewAction.ESCALATE,
            ReportReviewReason("review attachment context"),
            IntentKey("image-review-source"),
        )
    )
    history = await ReadReportReviewHistory(unit, HASHER, CODEC)(viewer.credential, report.id)
    assert history is not None
    assert history.report.kind.value == "message_image"
    assert history.report.context_id == report.context.id
    assert history.report.target_id == api.chat.sender.id
    assert history.current == result


async def test_actual_history_anchor_retains_original_decision_log_after_new_review(
    identity_engine: AsyncEngine,
) -> None:
    api = await reports(identity_engine)
    unit = SqlReportModerationUnitOfWork(
        api.uow.sessions, record_operator_audit, record_report_review_event
    )
    write = ReviewReport(unit, HASHER, FINGERPRINTER)
    for version in range(REVIEW_HISTORY_PAGE_SIZE + 1):
        await write(
            ReviewReportCommand(
                api.owner.credential,
                api.report.id,
                version,
                ReportReviewAction.DISMISS if version % 2 else ReportReviewAction.ESCALATE,
                ReportReviewReason("human reviewed decision"),
                IntentKey(str(uuid4())),
            )
        )
    read = ReadReportReviewHistory(unit, HASHER, CODEC)
    first = await read(api.owner.credential, api.report.id)
    assert first is not None
    assert len(first.revisions) == REVIEW_HISTORY_PAGE_SIZE
    assert first.next_cursor is not None
    newest = await write(
        ReviewReportCommand(
            api.owner.credential,
            api.report.id,
            REVIEW_HISTORY_PAGE_SIZE + 1,
            ReportReviewAction.DISMISS,
            ReportReviewReason("later decision"),
            IntentKey("later-human-review"),
        )
    )
    second = await read(api.owner.credential, api.report.id, first.next_cursor)
    assert second is not None
    assert tuple(row.version for row in second.revisions) == (1,)
    assert second.current == newest
    assert second.anchor_version == first.anchor_version
    assert second.next_cursor is None
