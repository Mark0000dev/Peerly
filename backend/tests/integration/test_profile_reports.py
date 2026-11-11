import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.safety.profile_reports import (
    ProfileReportPolicy,
    ProfileReportRateLimitedError,
    ReportContextUnavailableError,
    SubmitProfileReport,
    SubmitProfileReportCommand,
)
from studymate.domain.reports import ProfileAccessContext, ProfileReport, ReportCategory
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.profile_reports import (
    SqlProfileReportTransaction,
    SqlProfileReportUnitOfWork,
)
from studymate.infrastructure.persistence.report_models import (
    ProfileAccessRecord,
    ProfileReportIntentRecord,
    ProfileReportRecord,
)
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.migrations import run_revision_step
from tests.integration.safety_fixture import prepared
from tests.integration.student_actor import Actor

pytestmark = pytest.mark.integration
PRIVATE = "Private report detail retained only in business storage"


def service(engine: AsyncEngine, maximum: int = 10) -> SubmitProfileReport:
    return SubmitProfileReport(
        SqlProfileReportUnitOfWork(async_sessionmaker(engine, expire_on_commit=False)),
        Sha256SessionHasher(),
        HmacIntentFingerprinter(bytes(range(32))),
        ProfileReportPolicy(maximum_recent=maximum),
    )


def command(viewer: Actor, context: ProfileAccessContext) -> SubmitProfileReportCommand:
    return SubmitProfileReportCommand(
        viewer.credential, context.id, ReportCategory.OTHER, IntentKey(str(uuid4())), PRIVATE
    )


async def test_reports_replay_original_result_before_quota_and_reject_changed_payload(
    identity_engine: AsyncEngine,
) -> None:
    viewer, _, context = await prepared(identity_engine)
    submit = service(identity_engine, maximum=1)
    intent = command(viewer, context)
    original = await submit(intent)
    assert await submit(intent) == original
    with pytest.raises(IdempotencyConflictError):
        await submit(replace(intent, comment="Different private explanation"))
    with pytest.raises(ProfileReportRateLimitedError):
        await submit(replace(intent, intent_key=IntentKey(str(uuid4()))))
    async with async_sessionmaker(identity_engine)() as session:
        stored = (await session.scalars(select(ProfileReportRecord))).one()
        assert stored.comment == PRIVATE
        assert (
            await session.scalar(select(func.count()).select_from(ProfileReportIntentRecord)) == 1
        )
        transaction = SqlProfileReportTransaction(session)
        assert await transaction.own_report(viewer.id, original.id) == original
        assert await transaction.own_report(uuid4(), original.id) is None


async def test_concurrent_reports_serialize_actor_budget(identity_engine: AsyncEngine) -> None:
    viewer, _, context = await prepared(identity_engine)
    submit = service(identity_engine, maximum=1)

    async def attempt() -> ProfileReport | None:
        try:
            return await submit(command(viewer, context))
        except ProfileReportRateLimitedError:
            return None

    results = await asyncio.gather(attempt(), attempt())
    assert sum(result is not None for result in results) == 1


async def test_owned_disclosure_context_remains_reportable_after_target_deletion(
    identity_engine: AsyncEngine,
) -> None:
    viewer, target, context = await prepared(identity_engine)
    async with async_sessionmaker(identity_engine).begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == target.id)
            .values(deleted_at=func.clock_timestamp())
        )
    result = await service(identity_engine)(command(viewer, context))
    assert result.context == context
    assert result.context.snapshot.account_id == target.id


@pytest.mark.parametrize("foreign", [False, True])
async def test_unowned_and_unknown_access_contexts_are_neutral(
    identity_engine: AsyncEngine, foreign: bool
) -> None:
    viewer, target, context = await prepared(identity_engine)
    if foreign:
        async with async_sessionmaker(identity_engine).begin() as session:
            await session.execute(
                update(ProfileAccessRecord)
                .where(ProfileAccessRecord.id == context.id)
                .values(viewer_id=target.id, target_id=viewer.id, goal_id=None, goal_version=None)
            )
    else:
        context = replace(context, id=uuid4())
    with pytest.raises(ReportContextUnavailableError):
        await service(identity_engine)(command(viewer, context))


async def test_database_rejects_cross_actor_report_and_foreign_revision(
    identity_engine: AsyncEngine,
) -> None:
    viewer, target, context = await prepared(identity_engine)
    sessions = async_sessionmaker(identity_engine)
    with pytest.raises(IntegrityError):
        async with sessions.begin() as session:
            session.add(
                ProfileReportRecord(
                    id=uuid4(),
                    reporter_id=target.id,
                    context_id=context.id,
                    category="spam",
                    comment=None,
                    submitted_at=datetime.now(UTC),
                )
            )
    with pytest.raises(IntegrityError):
        async with sessions.begin() as session:
            await session.execute(
                update(ProfileAccessRecord)
                .where(ProfileAccessRecord.id == context.id)
                .values(goal_id=uuid4())
            )
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ProfileReportRecord)) == 0
        assert await session.get(AccountRecord, viewer.id) is not None


async def test_failed_report_transaction_keeps_no_partial_report_or_intent(
    identity_engine: AsyncEngine,
) -> None:
    viewer, _, context = await prepared(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    report = ProfileReport(uuid4(), viewer.id, context, ReportCategory.SPAM, datetime.now(UTC))

    async def failed_write() -> None:
        async with SqlProfileReportUnitOfWork(sessions).transaction() as transaction:
            await transaction.add_report(report)
            raise RuntimeError("controlled rollback")

    with pytest.raises(RuntimeError, match="controlled"):
        await failed_write()
    async with sessions() as session:
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


async def test_downgrade_refuses_to_erase_retained_disclosure_history(
    identity_engine: AsyncEngine,
) -> None:

    await prepared(identity_engine)
    with pytest.raises(RuntimeError, match="retained profile safety history"):
        async with identity_engine.begin() as connection:
            await connection.run_sync(run_revision_step, "0020_profile_reports", "downgrade")
    async with async_sessionmaker(identity_engine)() as session:
        assert await session.scalar(select(func.count()).select_from(ProfileAccessRecord)) == 1
