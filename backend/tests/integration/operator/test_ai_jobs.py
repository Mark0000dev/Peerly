"""Retained AI business inspection without task decoding, queue changes or secret-column loads."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.ai_jobs import ReadOperatorAiJob, ReadOperatorAiJobs
from studymate.application.operator.ai_ports import OperatorAiFilters
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.cursors import InvalidOperatorCursorError
from studymate.domain.ai.jobs import Failure, JobState
from studymate.domain.ai.tasks import AiKind
from studymate.domain.operator.ai_jobs import (
    OPERATOR_AI_INPUT_BYTES,
    OPERATOR_AI_MAX_ATTEMPTS,
    OPERATOR_AI_PAGE_SIZE,
    OPERATOR_AI_RESULT_BYTES,
)
from studymate.domain.operator.audit import OperatorAudit
from studymate.infrastructure.ai.models import (
    AiAttemptRecord,
    AiBudgetRecord,
    AiIntentRecord,
    AiJobRecord,
)
from studymate.infrastructure.operator.ai_cursors import FernetOperatorAiCursorCodec
from studymate.infrastructure.operator.ai_transactions import (
    SqlOperatorAiTransaction,
    SqlOperatorAiUnitOfWork,
)
from studymate.infrastructure.operator.models import (
    OperatorAccessRecord,
    OperatorAccessRevisionRecord,
    OperatorAuditRecord,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from tests.integration.operator.test_reads import operator
from tests.integration.profile_lifecycle_fixture import activated
from tests.integration.profile_lifecycle_fixture import command as hidden_command
from tests.integration.profile_lifecycle_fixture import services as visibility_services
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.student_actor import Actor, actor
from tests.unit.operator.ai_store import DIGEST, RAW_INPUT, RAW_RESULT

pytestmark = pytest.mark.integration
CODEC = FernetOperatorAiCursorCodec.from_key(b"j" * 32)
INTENT_KEY = "synthetic-private-ai-intent"
SOURCE_VERSION = 7


@dataclass(frozen=True, slots=True)
class Jobs:
    owner: Actor
    target: Actor
    job_id: UUID
    token: UUID
    origin_request_id: UUID
    uow: SqlOperatorAiUnitOfWork

    def jobs(self) -> ReadOperatorAiJobs:
        return ReadOperatorAiJobs(self.uow, HASHER, FINGERPRINTER, CODEC)

    def job(self) -> ReadOperatorAiJob:
        return ReadOperatorAiJob(self.uow, HASHER)


async def seed_job(
    session: AsyncSession,
    account_id: UUID,
    at: datetime,
    *,
    kind: AiKind = AiKind.CLARIFY_GOAL,
    state: JobState = JobState.SUCCEEDED,
) -> AiJobRecord:
    row = AiJobRecord(
        id=uuid4(),
        actor_id=account_id,
        kind=kind.value,
        source_id=uuid4(),
        source_version=SOURCE_VERSION,
        digest=DIGEST,
        input_json=RAW_INPUT,
        result_json=RAW_RESULT if state == JobState.SUCCEEDED else None,
        model=" retired model ",
        prompt=" legacy prompt ",
        schema_version=" unsupported schema ",
        adapter="old-adapter",
        state=state.value,
        created_at=at,
        deadline=at + timedelta(hours=1),
        not_before=at + timedelta(hours=2),
        attempts=3,
        generation=9,
        token=uuid4(),
        failure="timeout" if state == JobState.FAILED else None,
        request_id=uuid4(),
        action_id=None,
        trace_id=None,
        span_id=None,
    )
    session.add(row)
    await session.flush()
    return row


async def prepared(
    engine: AsyncEngine,
    *,
    kind: AiKind = AiKind.CLARIFY_GOAL,
    state: JobState = JobState.SUCCEEDED,
    target: Actor | None = None,
) -> Jobs:
    target = target if target is not None else await actor(engine)
    owner = await operator(engine)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        row = await seed_job(session, target.id, now - timedelta(days=1), kind=kind, state=state)
        assert row.token is not None
        assert row.request_id is not None
        for number in range(1, 4):
            started = row.created_at + timedelta(minutes=number)
            session.add(
                AiAttemptRecord(
                    job_id=row.id,
                    number=number,
                    token=uuid4(),
                    generation=number,
                    started_at=started,
                    ended_at=started + timedelta(seconds=1)
                    if number < OPERATOR_AI_MAX_ATTEMPTS
                    else None,
                    outcome="timeout" if number < OPERATOR_AI_MAX_ATTEMPTS else None,
                )
            )
        session.add(
            AiIntentRecord(
                actor_id=target.id, kind=kind.value, key=INTENT_KEY, job_id=row.id, digest=DIGEST
            )
        )
    return Jobs(
        owner,
        target,
        row.id,
        row.token,
        row.request_id,
        SqlOperatorAiUnitOfWork(sessions, record_operator_audit),
    )


@pytest.mark.parametrize("kind", list(AiKind))
async def test_all_actual_kinds_preserve_unsupported_raw_business_data_after_target_deletion(
    kind: AiKind, identity_engine: AsyncEngine
) -> None:
    api = await prepared(identity_engine, kind=kind)
    async with api.uow.sessions.begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == api.target.id)
            .values(banned_at=func.clock_timestamp(), deleted_at=func.clock_timestamp())
        )
    listing = await api.jobs()(api.owner.credential, api.target.id, OperatorAiFilters())
    assert listing is not None
    assert listing.jobs[0].kind == kind
    assert not hasattr(listing.jobs[0], "input_json_raw")
    actual = await api.job()(api.owner.credential, api.target.id, api.job_id)
    assert actual is not None
    assert actual.detail.input_json_raw == RAW_INPUT
    assert actual.detail.result_json_raw == RAW_RESULT
    assert actual.detail.input_digest == DIGEST
    assert actual.detail.job.source_version == SOURCE_VERSION
    assert actual.detail.job.versions.schema == " unsupported schema "
    assert actual.detail.job.origin.http_request_id == api.origin_request_id
    assert tuple(row.number for row in actual.detail.attempts_current) == (1, 2, 3)
    assert actual.detail.attempts_current[-1].outcome is None
    assert RAW_INPUT not in repr(actual)
    assert RAW_RESULT not in repr(actual.detail)
    async with api.uow.sessions() as session:
        row = await session.get(AiJobRecord, api.job_id)
        assert row is not None
        assert row.state == "succeeded"
        assert row.input_json == RAW_INPUT
        assert row.token == api.token
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
        assert len(audits) == len((listing, actual))
        assert all(
            item.action == "read_account"
            and item.requested_id == api.target.id
            and item.result_ids == [api.target.id]
            for item in audits
        )
        events = tuple(await session.scalars(select(ProductEventRecord)))
        assert all(
            item.kind == "operator.inspected" and item.operator_action == "read_account"
            for item in events
        )
        assert not tuple(await session.scalars(select(AiBudgetRecord)))
        assert (await session.scalars(select(AiIntentRecord.key))).one() == INTENT_KEY


async def test_hidden_target_and_expired_queued_state_are_retained_without_mutation(
    identity_engine: AsyncEngine,
) -> None:
    target = await activated(identity_engine)
    visibility, _ = visibility_services(identity_engine)
    await visibility(hidden_command(target))
    api = await prepared(identity_engine, target=target, state=JobState.QUEUED)
    actual = await api.job()(api.owner.credential, api.target.id, api.job_id)
    assert actual is not None
    assert actual.detail.job.state == JobState.QUEUED
    assert actual.detail.result_json_raw is None
    assert actual.detail.job.deadline < actual.observed_at
    async with api.uow.sessions() as session:
        assert (
            await session.scalar(select(AiJobRecord.state).where(AiJobRecord.id == api.job_id))
            == "queued"
        )


async def test_sql_metadata_does_not_fetch_payload_or_digest_and_all_reads_exclude_secret_columns(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine, state=JobState.RUNNING)
    statements: list[str] = []

    def capture(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _many: bool,
    ) -> None:
        statements.append(" ".join(statement.lower().split()))

    event.listen(identity_engine.sync_engine, "before_cursor_execute", capture)
    try:
        listing = await api.jobs()(api.owner.credential, api.target.id, OperatorAiFilters())
        assert listing is not None
        job_selects = [
            sql for sql in statements if sql.startswith("select ") and "from ai_jobs" in sql
        ]
        assert len(job_selects) == 1
        for private in (
            "ai_jobs.input_json",
            "ai_jobs.result_json",
            "ai_jobs.digest",
            "ai_jobs.token",
            "ai_jobs.generation",
        ):
            assert private not in job_selects[0]
        statements.clear()
        actual = await api.job()(api.owner.credential, api.target.id, api.job_id)
        assert actual is not None
        ai_selects = [
            sql
            for sql in statements
            if sql.startswith("select ") and ("from ai_jobs" in sql or "from ai_attempts" in sql)
        ]
        assert len(ai_selects) == len((1, 2))
        for sql in ai_selects:
            assert "ai_jobs.token" not in sql
            assert "ai_jobs.generation" not in sql
            assert "ai_attempts.token" not in sql
            assert "ai_attempts.generation" not in sql
            assert "ai_intents" not in sql
            assert "ai_executor_slot" not in sql
    finally:
        event.remove(identity_engine.sync_engine, "before_cursor_execute", capture)


async def test_metadata_keyset_filters_actual_future_anchor_and_refresh_current_state(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    async with api.uow.sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        for index in range(OPERATOR_AI_PAGE_SIZE + 2):
            await seed_job(
                session, api.target.id, now + timedelta(minutes=index), state=JobState.FAILED
            )
    filters = OperatorAiFilters(AiKind.CLARIFY_GOAL, JobState.FAILED, created_from=now)
    first = await api.jobs()(api.owner.credential, api.target.id, filters)
    assert first is not None
    assert first.next_cursor is not None
    assert len(first.jobs) == OPERATOR_AI_PAGE_SIZE
    assert first.anchor_created_at is not None
    assert first.anchor_created_at > first.observed_at
    assert first.jobs[0].failure == Failure.TIMEOUT
    async with api.uow.sessions.begin() as session:
        newer = await seed_job(
            session,
            api.target.id,
            first.anchor_created_at + timedelta(days=2),
            state=JobState.FAILED,
        )
    second = await api.jobs()(api.owner.credential, api.target.id, filters, first.next_cursor)
    assert second is not None
    assert len(second.jobs) == len((1, 2))
    assert second.next_cursor is None
    assert newer.id not in {row.id for row in second.jobs}
    with pytest.raises(InvalidOperatorCursorError):
        await api.jobs()(
            api.owner.credential, api.target.id, OperatorAiFilters(), first.next_cursor
        )
    upper = await api.jobs()(
        api.owner.credential, api.target.id, OperatorAiFilters(created_before=now)
    )
    assert upper is not None
    assert tuple(row.id for row in upper.jobs) == (api.job_id,)


async def test_current_attempt_observation_updates_without_fabricated_job_history(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    first = await api.job()(api.owner.credential, api.target.id, api.job_id)
    assert first is not None
    async with api.uow.sessions.begin() as session:
        await session.execute(
            update(AiAttemptRecord)
            .where(
                AiAttemptRecord.job_id == api.job_id,
                AiAttemptRecord.number == OPERATOR_AI_MAX_ATTEMPTS,
            )
            .values(outcome="executor_lost", ended_at=func.clock_timestamp())
        )
    current = await api.job()(api.owner.credential, api.target.id, api.job_id)
    assert current is not None
    assert current.detail.job == first.detail.job
    assert first.detail.attempts_current[-1].outcome is None
    assert current.detail.attempts_current[-1].outcome is not None
    assert current.detail.attempts_current[-1].outcome.value == "executor_lost"


async def test_parent_account_read_is_truthful_for_unknown_foreign_child_and_empty_account(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    empty = await actor(identity_engine)
    assert await api.job()(api.owner.credential, empty.id, api.job_id) is None
    assert await api.job()(api.owner.credential, api.target.id, uuid4()) is None
    missing = uuid4()
    assert await api.job()(api.owner.credential, missing, api.job_id) is None
    page = await api.jobs()(api.owner.credential, empty.id, OperatorAiFilters())
    assert page is not None
    assert not page.jobs
    assert await api.jobs()(api.owner.credential, missing, OperatorAiFilters()) is None
    async with api.uow.sessions() as session:
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
        assert all(
            item.outcome == "not_found" and item.result_ids == []
            for item in audits
            if item.requested_id == missing
        )
        assert all(
            item.outcome == "read" and item.result_ids == [item.requested_id]
            for item in audits
            if item.requested_id != missing
        )


async def test_current_operator_precedes_any_ai_source_query(identity_engine: AsyncEngine) -> None:
    api = await prepared(identity_engine)
    with pytest.raises(OperatorAccessDeniedError):
        await api.job()(api.target.credential, api.target.id, api.job_id)
    async with api.uow.sessions() as session:
        with pytest.raises(RuntimeError, match="operator"):
            await SqlOperatorAiTransaction(session, record_operator_audit).ai_jobs(
                api.target.id, OperatorAiFilters(), None
            )
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))


@pytest.mark.parametrize("read_detail", [True, False])
async def test_canonical_audit_failure_returns_no_private_data_and_rolls_back(
    read_detail: bool, identity_engine: AsyncEngine
) -> None:
    api = await prepared(identity_engine)

    async def failed(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        raise StorageUnavailableError

    uow = SqlOperatorAiUnitOfWork(api.uow.sessions, failed)
    operation = (
        ReadOperatorAiJob(uow, HASHER)(api.owner.credential, api.target.id, api.job_id)
        if read_detail
        else ReadOperatorAiJobs(uow, HASHER, FINGERPRINTER, CODEC)(
            api.owner.credential, api.target.id, OperatorAiFilters()
        )
    )
    with pytest.raises(StorageUnavailableError):
        await operation
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
        assert not tuple(await session.scalars(select(ProductEventRecord)))
        assert await session.get(AiJobRecord, api.job_id) is not None


async def test_final_session_expiry_after_actual_canonical_audit_uses_real_db_clock(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    async with api.uow.sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        await session.execute(
            update(SessionRecord)
            .where(SessionRecord.account_id == api.owner.id)
            .values(expires_at=now + timedelta(seconds=1))
        )
    entered = False

    async def expired(session: AsyncSession, audit: OperatorAudit) -> None:
        nonlocal entered
        await record_operator_audit(session, audit)
        entered = True
        await session.execute(select(func.pg_sleep(1.1)))

    uow = SqlOperatorAiUnitOfWork(api.uow.sessions, expired)
    with pytest.raises(UnauthenticatedError):
        await ReadOperatorAiJob(uow, HASHER)(api.owner.credential, api.target.id, api.job_id)
    assert entered
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
        assert not tuple(await session.scalars(select(ProductEventRecord)))


async def test_maximum_utf8_raw_payload_is_inspectable_without_current_decoder(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    raw_input = "é" * (OPERATOR_AI_INPUT_BYTES // 2)
    raw_result = "é" * (OPERATOR_AI_RESULT_BYTES // 2)
    async with api.uow.sessions.begin() as session:
        await session.execute(
            update(AiJobRecord)
            .where(AiJobRecord.id == api.job_id)
            .values(input_json=raw_input, result_json=raw_result)
        )
    result = await api.job()(api.owner.credential, api.target.id, api.job_id)
    assert result is not None
    assert result.detail.input_json_raw == raw_input
    assert result.detail.result_json_raw == raw_result


async def test_role_writer_waits_for_read_and_audit_commit_then_next_inspection_is_denied(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def paused(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        entered.set()
        await release.wait()

    uow = SqlOperatorAiUnitOfWork(api.uow.sessions, paused)
    read = asyncio.create_task(
        ReadOperatorAiJob(uow, HASHER)(api.owner.credential, api.target.id, api.job_id)
    )

    async def revoke() -> None:
        async with api.uow.sessions.begin() as session:
            await session.execute(
                select(AccountRecord.id).where(AccountRecord.id == api.owner.id).with_for_update()
            )
            await session.execute(
                select(SessionRecord.id)
                .where(SessionRecord.account_id == api.owner.id)
                .with_for_update()
            )
            root = await session.scalar(
                select(OperatorAccessRecord)
                .where(OperatorAccessRecord.account_id == api.owner.id)
                .with_for_update()
            )
            assert root is not None
            now = await session.scalar(select(func.clock_timestamp()))
            assert isinstance(now, datetime)
            root.current_version = 2
            session.add(
                OperatorAccessRevisionRecord(
                    account_id=api.owner.id, version=2, active=False, changed_at=now
                )
            )

    await asyncio.wait_for(entered.wait(), timeout=5)
    writer = asyncio.create_task(revoke())
    try:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(writer), timeout=0.05)
        release.set()
        assert await read is not None
        await writer
    finally:
        release.set()
        await read
        await writer
    with pytest.raises(OperatorAccessDeniedError):
        await api.job()(api.owner.credential, api.target.id, api.job_id)
