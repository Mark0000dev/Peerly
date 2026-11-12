import asyncio
from datetime import datetime, timedelta

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.report_triage import ReadReportTriageContext
from studymate.infrastructure.operator.models import (
    OperatorAccessRecord,
    OperatorAccessRevisionRecord,
    OperatorAuditRecord,
)
from studymate.infrastructure.operator.report_triage_identity import lock_triage_identity
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from tests.integration.operator.report_triage.fixture import CODEC, prepared
from tests.integration.requests.fixture import HASHER
from tests.integration.test_email_verification import actor as pending_actor
from tests.integration.test_email_verification import services, start_command

pytestmark = pytest.mark.integration


async def test_complete_batched_snapshot_equals_canonical_actual_facts(
    ai_engine: AsyncEngine,
) -> None:
    api = await prepared(ai_engine)
    pending = await pending_actor(ai_engine)
    start, _verify = services(ai_engine)
    await start(start_command(pending))
    sessions = async_sessionmaker(ai_engine, expire_on_commit=False)
    for credential in (
        api.reports.owner.credential,
        api.reports.reporter.credential,
        api.reports.target.credential,
        pending,
    ):
        digest = await HASHER.digest(credential)
        async with sessions.begin() as session:
            expected = await SqlIdentityTransaction(session).lock_identity(digest)
        async with sessions.begin() as session:
            actual = await lock_triage_identity(session, digest, api.reports.target.id)
        assert actual == expected
        assert actual is not None
    async with sessions.begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == api.reports.owner.id)
            .values(banned_at=func.clock_timestamp(), deleted_at=func.clock_timestamp())
        )
    digest = await HASHER.digest(api.reports.owner.credential)
    async with sessions.begin() as session:
        expected = await SqlIdentityTransaction(session).lock_identity(digest)
    async with sessions.begin() as session:
        assert await lock_triage_identity(session, digest, api.reports.target.id) == expected


async def test_future_actual_role_cannot_bind_or_expose_private_source(
    ai_engine: AsyncEngine,
) -> None:
    api = await prepared(ai_engine)
    async with api.unit.sessions.begin() as session:
        at = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(at, datetime)
        session.add(
            OperatorAccessRevisionRecord(
                account_id=api.reports.owner.id,
                version=2,
                active=True,
                changed_at=at + timedelta(days=1),
            )
        )
        await session.flush()
        await session.execute(
            update(OperatorAccessRecord)
            .where(OperatorAccessRecord.account_id == api.reports.owner.id)
            .values(current_version=2)
        )
    with pytest.raises(OperatorAccessDeniedError):
        await ReadReportTriageContext(api.unit, HASHER, CODEC)(
            api.reports.owner.credential, api.reports.report.id
        )
    async with api.unit.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(OperatorAuditRecord)) == 0


async def test_unbound_factual_identity_never_becomes_operator_authority(
    ai_engine: AsyncEngine,
) -> None:
    api = await prepared(ai_engine)
    digest = await HASHER.digest(api.reports.owner.credential)
    async with api.unit.transaction(digest, api.reports.report.id) as transaction:
        facts = await transaction.lock_triage_authority(digest)
        assert facts.identity is not None
        assert facts.access is not None
        with pytest.raises(RuntimeError, match="application-validated"):
            await transaction.lock_triage_context(api.reports.report.id)


async def test_session_expiry_during_real_role_lock_wait_has_no_private_result(
    ai_engine: AsyncEngine,
) -> None:
    api = await prepared(ai_engine)
    role_started = asyncio.Event()

    def observe(*arguments: object) -> None:
        statement = arguments[2]
        if (
            isinstance(statement, str)
            and "FROM operator_access_revisions" in statement
            and "FOR UPDATE" in statement
        ):
            role_started.set()

    async with api.unit.sessions.begin() as session:
        at = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(at, datetime)
        await session.execute(
            update(SessionRecord)
            .where(SessionRecord.account_id == api.reports.owner.id)
            .values(expires_at=at + timedelta(seconds=0.5))
        )
    async with api.unit.sessions() as blocker:
        await blocker.execute(
            select(OperatorAccessRecord)
            .where(OperatorAccessRecord.account_id == api.reports.owner.id)
            .with_for_update()
        )
        event.listen(ai_engine.sync_engine, "before_cursor_execute", observe)
        task = asyncio.create_task(
            ReadReportTriageContext(api.unit, HASHER, CODEC)(
                api.reports.owner.credential, api.reports.report.id
            )
        )
        try:
            await asyncio.wait_for(role_started.wait(), 1)
            assert not task.done()
            await blocker.execute(select(func.pg_sleep(0.6)))
            await blocker.commit()
            with pytest.raises(UnauthenticatedError):
                await task
        finally:
            event.remove(ai_engine.sync_engine, "before_cursor_execute", observe)
            await blocker.rollback()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    async with api.unit.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(OperatorAuditRecord)) == 0
