"""Head49 actual unified report journal, owned FK evidence and transaction races."""

import asyncio
from dataclasses import replace
from datetime import datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from studymate.application.discovery.profiles import ReadDiscoveryProfile
from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.safety.message_reports import SubmitMessageImageReport
from studymate.application.safety.profile_reports import (
    ProfileReportRateLimitedError,
    ReportContextUnavailableError,
    ReportIntent,
    SubmitProfileReport,
    SubmitProfileReportCommand,
)
from studymate.domain.message_reports import MessageImageReport
from studymate.domain.reports import ReportCategory
from studymate.infrastructure.persistence.discovery_profiles import SqlDiscoveryProfileUnitOfWork
from studymate.infrastructure.persistence.message_report_models import MessageReportContextRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_message_report_event
from studymate.infrastructure.persistence.profile_reports import SqlProfileReportUnitOfWork
from studymate.infrastructure.persistence.report_models import (
    ProfileReportIntentRecord,
    ProfileReportRecord,
)
from studymate.infrastructure.safety.message_reports import (
    SqlMessageReportTransaction,
    SqlMessageReportUnitOfWork,
)
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.safety.message_reports.fixture import prepared

pytestmark = pytest.mark.integration
PROFILE_REPORTS_BEFORE_RACE = 9
TOTAL_SHARED_LIMIT = 10


async def test_concurrent_retry_retains_one_actual_message_image_report_and_canonical(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    first, second = await asyncio.gather(api.submit()(api.command()), api.submit()(api.command()))
    assert first == second
    with pytest.raises(IdempotencyConflictError):
        await api.submit()(replace(api.command(), comment="Altered payload"))
    async with api.chat.api.sessions() as session:
        root = (await session.scalars(select(ProfileReportRecord))).one()
        assert root.kind == "message_image"
        assert root.context_id is None
        assert root.message_context_id == api.context.id
        assert root.comment == first.comment
        assert (
            await session.scalar(select(func.count()).select_from(ProfileReportIntentRecord)) == 1
        )
        event = (
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "report.created")
            )
        ).one()
        assert event.report_id == first.id
        assert event.account_id == api.chat.recipient.id
        assert "Private" not in repr(event.__dict__)
        assert first.context.source.image is not None


async def test_shared_profile_quota_serializes_mixed_kind_last_slot_and_intent_namespace(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    profile = await ReadDiscoveryProfile(
        SqlDiscoveryProfileUnitOfWork(api.chat.api.sessions), HASHER
    )(api.chat.recipient.credential, api.chat.sender.id)
    profile_submit = SubmitProfileReport(
        SqlProfileReportUnitOfWork(api.chat.api.sessions), HASHER, FINGERPRINTER
    )
    for number in range(PROFILE_REPORTS_BEFORE_RACE):
        await profile_submit(
            SubmitProfileReportCommand(
                api.chat.recipient.credential,
                profile.access_context.id,
                ReportCategory.SPAM,
                IntentKey(f"profile-report-{number}"),
            )
        )
    with pytest.raises(IdempotencyConflictError):
        await api.submit()(api.command("profile-report-0"))

    async def attempt(key: str) -> MessageImageReport | None:
        try:
            return await api.submit()(api.command(key))
        except ProfileReportRateLimitedError:
            return None

    results = await asyncio.gather(attempt("last-slot-one"), attempt("last-slot-two"))
    assert sum(result is not None for result in results) == 1
    retained = next(result for result in results if result is not None)
    with pytest.raises(IdempotencyConflictError):
        await profile_submit(
            SubmitProfileReportCommand(
                api.chat.recipient.credential,
                profile.access_context.id,
                ReportCategory.SPAM,
                IntentKey("last-slot-one" if results[0] is not None else "last-slot-two"),
            )
        )
    async with api.chat.api.sessions() as session:
        assert (
            await session.scalar(select(func.count()).select_from(ProfileReportRecord))
            == TOTAL_SHARED_LIMIT
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProfileReportRecord)
                .where(ProfileReportRecord.kind == "message_image")
            )
            == 1
        )
    assert retained.context == api.context


@pytest.mark.parametrize("cancelled", [False, True])
async def test_real_canonical_callback_failure_rolls_back_report_intent_and_event(
    identity_engine: AsyncEngine, cancelled: bool
) -> None:
    api = await prepared(identity_engine)

    async def interrupted(session: AsyncSession, report: MessageImageReport) -> None:
        await record_message_report_event(session, report)
        if cancelled:
            raise asyncio.CancelledError
        raise RuntimeError("synthetic canonical post-write failure")

    submit = SubmitMessageImageReport(
        SqlMessageReportUnitOfWork(api.chat.api.sessions, interrupted), HASHER, FINGERPRINTER
    )
    error = asyncio.CancelledError if cancelled else RuntimeError
    with pytest.raises(error):
        await submit(api.command())
    async with api.chat.api.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ProfileReportRecord)) == 0
        assert (
            await session.scalar(select(func.count()).select_from(ProfileReportIntentRecord)) == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProductEventRecord)
                .where(ProductEventRecord.kind == "report.created")
            )
            == 0
        )
        assert await session.get(MessageReportContextRecord, api.context.id) is not None
    assert (await api.submit()(api.command())).context == api.context


async def test_final_original_session_deadline_rolls_back_real_report(
    identity_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = await prepared(identity_engine)
    original_remember = SqlMessageReportTransaction.remember_report_intent
    original_now = SqlMessageReportTransaction.now
    written = False
    async with api.chat.api.sessions() as session:
        from studymate.infrastructure.persistence.identity_models import SessionRecord

        expiry = (
            await session.scalars(
                select(SessionRecord.expires_at).where(
                    SessionRecord.account_id == api.chat.recipient.id
                )
            )
        ).one()

    async def remember(
        tx: SqlMessageReportTransaction,
        actor_id: UUID,
        key: IntentKey,
        intent: ReportIntent,
        at: datetime,
    ) -> None:
        nonlocal written
        await original_remember(tx, actor_id, key, intent, at)
        written = True

    async def now(tx: SqlMessageReportTransaction) -> datetime:
        return expiry if written else await original_now(tx)

    monkeypatch.setattr(SqlMessageReportTransaction, "remember_report_intent", remember)
    monkeypatch.setattr(SqlMessageReportTransaction, "now", now)
    with pytest.raises(UnauthenticatedError):
        await api.submit()(api.command())
    async with api.chat.api.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ProfileReportRecord)) == 0
        assert (
            await session.scalar(select(func.count()).select_from(ProfileReportIntentRecord)) == 0
        )


@pytest.mark.parametrize("fault", ["image", "author", "shape"])
async def test_database_rejects_wrong_actual_message_image_or_report_discriminator(
    identity_engine: AsyncEngine, fault: str
) -> None:
    api = await prepared(identity_engine)
    report = await api.submit()(api.command())

    async def violate() -> None:
        async with api.chat.api.sessions.begin() as session:
            if fault == "image":
                await session.execute(
                    update(MessageReportContextRecord)
                    .where(MessageReportContextRecord.id == api.context.id)
                    .values(image_id=uuid4())
                )
            elif fault == "author":
                await session.execute(
                    update(MessageReportContextRecord)
                    .where(MessageReportContextRecord.id == api.context.id)
                    .values(target_id=api.chat.recipient.id)
                )
            else:
                await session.execute(
                    update(ProfileReportRecord)
                    .where(ProfileReportRecord.id == report.id)
                    .values(kind="profile")
                )

    with pytest.raises(IntegrityError):
        await violate()
    assert await api.submit()(api.command()) == report


async def test_unknown_context_never_invents_conversation_or_report_authority(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    with pytest.raises(ReportContextUnavailableError):
        await api.submit()(replace(api.command(), context_id=uuid4()))
    async with api.chat.api.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ProfileReportRecord)) == 0


async def test_earlier_observed_server_timestamp_does_not_break_actual_context_fk_causality(
    identity_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = await prepared(identity_engine)
    # Use an actual earlier DB-observed message timestamp, not a host wall clock
    # or a changed PostgreSQL clock. The immutable context/message FK proves order.
    observed_at = api.context.source.sent_at
    assert observed_at < api.context.issued_at

    async def earlier_clock(tx: SqlMessageReportTransaction) -> datetime:
        del tx
        return observed_at

    monkeypatch.setattr(SqlMessageReportTransaction, "now", earlier_clock)
    report = await api.submit()(api.command())
    assert report.submitted_at == observed_at
    assert report.submitted_at < report.context.issued_at
    async with api.chat.api.sessions() as session:
        source = await session.get(ProfileReportRecord, report.id)
        assert source is not None
        assert source.message_context_id == api.context.id
        assert source.submitted_at == observed_at
        event = (
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.report_id == report.id)
            )
        ).one()
        assert event.occurred_at == observed_at
