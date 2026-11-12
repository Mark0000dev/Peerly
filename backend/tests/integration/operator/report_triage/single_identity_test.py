import asyncio
import json
from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import OperatorAccessDeniedError, require_operator
from studymate.application.operator.report_triage import (
    EnqueueReportTriage,
    EnqueueReportTriageCommand,
    ReadReportTriage,
    ReadReportTriageContext,
)
from studymate.domain.operator.audit import OperatorAudit
from studymate.infrastructure.ai.models import AiJobRecord
from studymate.infrastructure.operator.models import (
    OperatorAccessRecord,
    OperatorAccessRevisionRecord,
    OperatorAuditRecord,
)
from studymate.infrastructure.operator.report_triage_transactions import (
    SqlOperatorReportTriageUnitOfWork,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord
from studymate.infrastructure.persistence.product_events import (
    record_operator_audit,
    record_report_triage_submission,
)
from tests.integration.operator.report_triage.fixture import CODEC, prepared
from tests.integration.operator.report_triage.measurements import ACTIVE_OPERATION, Measurements
from tests.integration.operator.report_triage.worker_test import revoke_grant
from tests.integration.requests.fixture import FINGERPRINTER, HASHER

pytestmark = pytest.mark.integration


async def test_each_triage_usecase_locks_actual_identity_once_before_report(
    ai_engine: AsyncEngine,
    record_property: Callable[[str, object], None],
) -> None:
    api = await prepared(ai_engine)
    observed: list[str] = []
    queries: list[str] = []
    measurements = Measurements()
    token = ACTIVE_OPERATION.set("three_actual_usecases")

    def observe(*arguments: object) -> None:
        statement = arguments[2]
        if not isinstance(statement, str):
            return
        queries.append(statement.split(maxsplit=1)[0])
        if statement.startswith("SELECT accounts.id") and "AS actor_id" in statement:
            observed.extend(("credential_scope", "account_lock"))
        elif "FROM accounts" in statement and "FOR NO KEY UPDATE" in statement:
            observed.append("account_lock")
        elif "FROM sessions" in statement and "FOR NO KEY UPDATE" in statement:
            observed.append("session_lock")
        elif "FROM profile_reports" in statement and "FOR UPDATE" in statement:
            observed.append("report_lock")

    def assert_scope(operation: str) -> None:
        assert observed.count("credential_scope") == 1
        assert observed.index("account_lock") < observed.index("session_lock")
        assert observed.index("session_lock") < observed.index("report_lock")
        record_property(operation + "_selects", queries.count("SELECT"))
        record_property(operation + "_statements", len(queries))
        record_property(operation + "_roundtrips", json.dumps(measurements.queries))
        record_property(
            operation + "_operation_to_checkout_seconds", json.dumps(measurements.checkout)
        )
        record_property(operation + "_connection_held_seconds", json.dumps(measurements.held))
        measurements.reset()
        observed.clear()
        queries.clear()

    event.listen(ai_engine.sync_engine, "before_cursor_execute", observe)
    measurements.install(ai_engine)
    try:
        source = await ReadReportTriageContext(api.unit, HASHER, CODEC)(
            api.reports.owner.credential,
            api.reports.report.id,
        )
        assert source is not None
        assert source.source_token is not None
        assert_scope("preview")
        submitted = await EnqueueReportTriage(api.unit, HASHER, FINGERPRINTER, CODEC)(
            EnqueueReportTriageCommand(
                api.reports.owner.credential,
                api.reports.report.id,
                source.source_token,
                IntentKey(str(uuid4())),
            ),
        )
        assert_scope("enqueue")
        read = await ReadReportTriage(api.unit, HASHER)(
            api.reports.owner.credential, api.reports.report.id
        )
        assert read is not None
        assert read.triage is not None
        assert read.triage.submission == submitted.submission
        assert_scope("read")
    finally:
        event.remove(ai_engine.sync_engine, "before_cursor_execute", observe)
        measurements.close(ai_engine)
        ACTIVE_OPERATION.reset(token)


async def test_typed_transaction_cannot_authenticate_outside_original_actor_scope(
    ai_engine: AsyncEngine,
) -> None:
    api = await prepared(ai_engine)
    with pytest.raises(RuntimeError, match="differs from its actual scoped actor"):
        async with api.unit.transaction(b"x" * 32, api.reports.report.id) as transaction:
            await require_operator(transaction, api.reports.owner.credential, HASHER)
    async with api.unit.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(OperatorAuditRecord)) == 0


@pytest.mark.parametrize(
    "condition", ["absent_role", "revoked_role", "banned", "deleted", "revoked_session"]
)
async def test_all_three_operations_require_actual_live_authority(
    ai_engine: AsyncEngine, condition: str
) -> None:
    api = await prepared(ai_engine)
    command = await api.command()
    viewer = api.reports.owner
    expected: type[Exception] = OperatorAccessDeniedError
    if condition == "absent_role":
        viewer = api.reports.reporter
    elif condition == "revoked_role":
        await revoke_grant(api)
    else:
        async with api.unit.sessions.begin() as session:
            if condition == "revoked_session":
                await session.execute(
                    update(SessionRecord)
                    .where(SessionRecord.account_id == viewer.id)
                    .values(revoked_at=func.clock_timestamp())
                )
                expected = UnauthenticatedError
            else:
                values = {
                    "banned_at" if condition == "banned" else "deleted_at": func.clock_timestamp()
                }
                await session.execute(
                    update(AccountRecord).where(AccountRecord.id == viewer.id).values(**values)
                )
                if condition == "deleted":
                    expected = UnauthenticatedError
    async with api.unit.sessions() as session:
        before = await session.scalar(select(func.count()).select_from(OperatorAuditRecord))
    with pytest.raises(expected):
        await ReadReportTriageContext(api.unit, HASHER, CODEC)(
            viewer.credential, api.reports.report.id
        )
    with pytest.raises(expected):
        await api.enqueue()(
            EnqueueReportTriageCommand(
                viewer.credential, command.report_id, command.source_token, command.intent_key
            )
        )
    with pytest.raises(expected):
        await ReadReportTriage(api.unit, HASHER)(viewer.credential, api.reports.report.id)
    async with api.unit.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(OperatorAuditRecord)) == before
        assert await session.scalar(select(func.count()).select_from(AiJobRecord)) == 0


async def test_concurrent_grant_revocation_is_observed_after_actual_role_lock(
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

    async with api.unit.sessions() as blocker:
        await blocker.execute(
            select(OperatorAccessRecord)
            .where(OperatorAccessRecord.account_id == api.reports.owner.id)
            .with_for_update()
        )
        # The revoke is uncommitted while the actual reader starts and blocks on the role.
        event.listen(ai_engine.sync_engine, "before_cursor_execute", observe)
        task = asyncio.create_task(
            ReadReportTriageContext(api.unit, HASHER, CODEC)(
                api.reports.owner.credential, api.reports.report.id
            )
        )
        try:
            await asyncio.wait_for(role_started.wait(), 1)
            assert not task.done()
            # Insert/update in this already-locked transaction, not another writer.
            at = await blocker.scalar(select(func.clock_timestamp()))
            blocker.add(
                OperatorAccessRevisionRecord(
                    account_id=api.reports.owner.id, version=2, active=False, changed_at=at
                )
            )
            await blocker.flush()
            await blocker.execute(
                update(OperatorAccessRecord)
                .where(OperatorAccessRecord.account_id == api.reports.owner.id)
                .values(current_version=2)
            )
            await blocker.commit()
            with pytest.raises(OperatorAccessDeniedError):
                await task
        finally:
            event.remove(ai_engine.sync_engine, "before_cursor_execute", observe)
            await blocker.rollback()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    async with api.unit.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(OperatorAuditRecord)) == 0


async def test_fresh_finish_clock_expiry_rolls_back_preview_audit(
    ai_engine: AsyncEngine,
) -> None:
    api = await prepared(ai_engine)
    async with api.unit.sessions.begin() as session:
        at = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(at, datetime)
        await session.execute(
            update(SessionRecord)
            .where(SessionRecord.account_id == api.reports.owner.id)
            .values(expires_at=at + timedelta(seconds=0.5))
        )

    async def expire_during_audit(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        await session.execute(select(func.pg_sleep(0.6)))

    unit = SqlOperatorReportTriageUnitOfWork(
        api.unit.sessions, expire_during_audit, record_report_triage_submission
    )
    with pytest.raises(UnauthenticatedError):
        await ReadReportTriageContext(unit, HASHER, CODEC)(
            api.reports.owner.credential, api.reports.report.id
        )
    async with api.unit.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(OperatorAuditRecord)) == 0
