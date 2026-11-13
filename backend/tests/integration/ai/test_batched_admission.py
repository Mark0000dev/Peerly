import asyncio
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.ai.ports import Admission, AiUnavailableError
from studymate.application.idempotency import IntentKey
from studymate.application.identity.registration import (
    BeginRegistrationCommand,
    CompleteRegistrationCommand,
)
from studymate.application.identity.sessions import IdentitySnapshot
from studymate.domain.ai.tasks import ClarifyGoal, Source
from studymate.domain.membership import GOOGLE_ISSUER
from studymate.infrastructure.ai.admission_slot import (
    AdmissionSlotLock,
    acquire_admission_slot,
    ensure_admission_slot,
)
from studymate.infrastructure.ai.models import AiJobRecord, AiSlotRecord
from studymate.infrastructure.ai.persistence import SqlAiTransaction
from studymate.infrastructure.persistence.identity_claims import retire_deleted_claims
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
    SessionRecord,
)
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.ai.test_admission_counts import RetainedJob, record
from tests.integration.ai.test_queue import VERSIONS, goal, services, submission
from tests.integration.onboarding_fixture import ready_setup
from tests.integration.registration_fixture import documents
from tests.integration.student_actor import actor
from tests.integration.test_registration import registration

pytestmark = pytest.mark.integration
ACTIVE: ContextVar[bool] = ContextVar("batched_admission_query", default=False)
ROUNDTRIP_LIMIT = 18


@dataclass(slots=True)
class Queries:
    count: int = 0
    slot_locks: int = 0

    def before(self, *args: object) -> None:
        if ACTIVE.get():
            self.count += 1
            sql = args[2]
            if isinstance(sql, str) and "ai_executor_slot" in sql and "FOR UPDATE" in sql:
                self.slot_locks += 1


@pytest.mark.parametrize("complete", [False, True])
async def test_full_snapshot_preserves_actual_registration_and_activation_sources(
    identity_engine: AsyncEngine, complete: bool
) -> None:
    owner = await actor(identity_engine)
    if complete:
        await documents(identity_engine)
        begin, finish, _ = registration(identity_engine)
        context = await begin(BeginRegistrationCommand(owner.credential, IntentKey(str(uuid4()))))
        await ready_setup(identity_engine, owner.credential)
        await finish(
            CompleteRegistrationCommand(owner.credential, context.id, IntentKey(str(uuid4())))
        )
    digest = await Sha256SessionHasher().digest(owner.credential)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        expected = await SqlIdentityTransaction(session).lock_identity(digest)
    async with sessions.begin() as session:
        actual = await SqlAiTransaction(session).lock_identity(digest)
    assert actual == expected
    assert actual is not None
    assert actual.activation_complete is complete
    assert (actual.registration is not None) is complete


async def test_lineage_ban_committed_during_session_lock_wait_is_not_read_from_prelock_snapshot(
    identity_engine: AsyncEngine,
) -> None:
    previous, current = await actor(identity_engine), await actor(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        at = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(at, datetime)
        await session.execute(
            update(AccountRecord).where(AccountRecord.id == previous.id).values(deleted_at=at)
        )
        await retire_deleted_claims(session, previous.id)
        session.add_all(
            [
                ExternalIdentityRecord(
                    id=uuid4(),
                    account_id=previous.id,
                    issuer=GOOGLE_ISSUER,
                    subject="shared-retained-ban",
                    created_at=at,
                    retired_at=at,
                ),
                ExternalIdentityRecord(
                    id=uuid4(),
                    account_id=current.id,
                    issuer=GOOGLE_ISSUER,
                    subject="shared-retained-ban",
                    created_at=at,
                ),
            ]
        )
    digest = await Sha256SessionHasher().digest(current.credential)
    async with sessions.begin() as blocker:
        await blocker.execute(
            select(SessionRecord.id).where(SessionRecord.account_id == current.id).with_for_update()
        )
        pid_ready: asyncio.Future[int] = asyncio.get_running_loop().create_future()

        async def read_locked_identity() -> IdentitySnapshot | None:
            async with sessions.begin() as reader:
                pid = await reader.scalar(select(func.pg_backend_pid()))
                assert isinstance(pid, int)
                pid_ready.set_result(pid)
                return await SqlAiTransaction(reader).lock_identity(digest)

        task = asyncio.create_task(read_locked_identity())
        try:
            pid = await pid_ready
            async with asyncio.timeout(2):
                while True:
                    async with sessions() as observer:
                        blockers = await observer.scalar(select(func.pg_blocking_pids(pid)))
                    if blockers:
                        break
                    await asyncio.sleep(0)
            async with sessions.begin() as changed:
                await changed.execute(
                    update(AccountRecord)
                    .where(AccountRecord.id == previous.id)
                    .values(banned_at=func.clock_timestamp())
                )
            await blocker.commit()
            actual = await task
            assert actual is not None
            assert actual.banned
        finally:
            if not task.done():
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task


@pytest.mark.parametrize("boundary", ["commit", "savepoint", "other_session"])
async def test_slot_lock_proof_never_survives_transaction_or_session_boundaries(
    ai_engine: AsyncEngine, boundary: str
) -> None:
    sessions = async_sessionmaker(ai_engine, expire_on_commit=False)
    cache = AdmissionSlotLock()
    async with sessions() as session:
        if boundary == "savepoint":
            async with session.begin():
                nested = await session.begin_nested()
                await acquire_admission_slot(session, cache)
                await nested.rollback()
                assert not cache.consume(session)
                await ensure_admission_slot(session, cache)
        elif boundary == "commit":
            async with session.begin():
                await acquire_admission_slot(session, cache)
            async with session.begin():
                assert not cache.consume(session)
                await ensure_admission_slot(session, cache)
        else:
            async with session.begin():
                await acquire_admission_slot(session, cache)
                async with sessions() as other:
                    assert not cache.consume(other)


async def test_reused_slot_lock_still_reads_real_changed_runtime_facts(
    ai_engine: AsyncEngine,
) -> None:
    owner = await actor(ai_engine)
    sessions = async_sessionmaker(ai_engine, expire_on_commit=False)
    intent = Admission(
        owner.id,
        ClarifyGoal(Source(uuid4(), 1), "synthetic source"),
        IntentKey(str(uuid4())),
        b"q" * 32,
        VERSIONS,
    )

    async def changed_runtime_admission() -> None:
        async with sessions.begin() as session:
            transaction = SqlAiTransaction(session)
            await transaction.runtime_versions(await transaction.now())
            at = await session.scalar(select(func.clock_timestamp()))
            assert isinstance(at, datetime)
            await session.execute(
                update(AiSlotRecord)
                .where(AiSlotRecord.id == 1)
                .values(
                    runtime_started_at=at - timedelta(seconds=30),
                    runtime_heartbeat_at=at - timedelta(seconds=20),
                    runtime_valid_until=at - timedelta(seconds=5),
                )
                .execution_options(synchronize_session=False)
            )
            await transaction.admit(intent, at)

    with pytest.raises(AiUnavailableError):
        await changed_runtime_admission()
    async with sessions() as session:
        assert not tuple(await session.scalars(select(AiJobRecord)))


@pytest.mark.parametrize("expired", [False, True])
async def test_real_student_submit_is_bounded_roundtrips_and_preserves_terminal_recorder(
    ai_engine: AsyncEngine, expired: bool
) -> None:
    owner, other = await actor(ai_engine), await actor(ai_engine)
    source, other_source = await goal(ai_engine, owner), await goal(ai_engine, other)
    sessions = async_sessionmaker(ai_engine, expire_on_commit=False)
    old = None
    if expired:
        old = record(owner, other, source, other_source, RetainedJob(expired=True))
        async with sessions.begin() as session:
            session.add(old)
    counter = Queries()
    event.listen(ai_engine.sync_engine, "before_cursor_execute", counter.before)
    token = ACTIVE.set(True)
    try:
        created = await services(ai_engine).submit(
            owner.credential, submission(source), IntentKey(str(uuid4()))
        )
    finally:
        ACTIVE.reset(token)
        event.remove(ai_engine.sync_engine, "before_cursor_execute", counter.before)
    assert counter.count <= ROUNDTRIP_LIMIT
    assert counter.slot_locks == 1
    async with sessions() as session:
        actual = await session.get(AiJobRecord, created.id)
        assert actual is not None
        assert actual.state == "queued"
        if old is not None:
            retained = await session.get(AiJobRecord, old.id)
            assert retained is not None
            assert retained.state == "expired"
            outcomes = tuple(
                await session.scalars(
                    select(ProductEventRecord).where(ProductEventRecord.ai_job_id == old.id)
                )
            )
            assert len(outcomes) == 1
            assert outcomes[0].ai_state == "expired"


async def test_atomic_write_failure_rolls_back_budget_intent_and_prior_terminal_event(
    ai_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from studymate.infrastructure.ai import persistence
    from studymate.infrastructure.ai.models import AiBudgetRecord, AiIntentRecord

    owner, other = await actor(ai_engine), await actor(ai_engine)
    source, other_source = await goal(ai_engine, owner), await goal(ai_engine, other)
    retained = record(owner, other, source, other_source, RetainedJob(expired=True))
    sessions = async_sessionmaker(ai_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        session.add(retained)
    monkeypatch.setattr(persistence, "uuid4", lambda: retained.id)
    with pytest.raises(IntegrityError):
        await services(ai_engine).submit(
            owner.credential, submission(source), IntentKey(str(uuid4()))
        )
    async with sessions() as session:
        old = await session.get(AiJobRecord, retained.id)
        assert old is not None
        assert old.state == "queued"
        assert await session.get(AiBudgetRecord, owner.id) is None
        assert not tuple(
            await session.scalars(select(AiIntentRecord).where(AiIntentRecord.actor_id == owner.id))
        )
        assert not tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.ai_job_id == retained.id)
            )
        )


async def test_shared_identity_mode_and_readonly_mutation_guard_are_preserved(
    ai_engine: AsyncEngine,
) -> None:
    from studymate.infrastructure.persistence.transactions import open_transaction

    owner = await actor(ai_engine)
    sessions = async_sessionmaker(ai_engine, expire_on_commit=False)
    digest = await Sha256SessionHasher().digest(owner.credential)
    intent = Admission(
        owner.id,
        ClarifyGoal(Source(uuid4(), 1), "synthetic read-only guard"),
        IntentKey(str(uuid4())),
        b"r" * 32,
        VERSIONS,
    )

    async def attempt_mutation() -> None:
        async with open_transaction(sessions, read_only=True) as session:
            transaction = SqlAiTransaction(session, shared_identity_locks=True)
            identity = await transaction.lock_identity(digest)
            assert identity is not None
            assert identity.session.account_id == owner.id
            await transaction.runtime_versions(await transaction.now())
            await transaction.admit(intent, await transaction.now())

    with pytest.raises(RuntimeError, match="Read-only identity unit cannot execute mutations"):
        await attempt_mutation()
    async with sessions() as session:
        assert not tuple(await session.scalars(select(AiJobRecord)))
