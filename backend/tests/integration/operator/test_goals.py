"""Actual retained goal records, owner scope and truthful non-replay keyset semantics."""

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.goal_ports import OperatorGoalFilters, OperatorGoalState
from studymate.application.operator.goals import ReadOperatorGoalHistory, ReadOperatorGoals
from studymate.domain.catalogue import subject_key
from studymate.domain.operator.audit import OperatorAudit
from studymate.domain.operator.goals import OPERATOR_GOAL_PAGE_SIZE
from studymate.domain.study_context import CanonicalSubjectRef, GoalContent
from studymate.infrastructure.operator.goal_cursors import FernetOperatorGoalCursorCodec
from studymate.infrastructure.operator.goal_transactions import (
    SqlOperatorGoalTransaction,
    SqlOperatorGoalUnitOfWork,
)
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.persistence.catalogue_models import SubjectRecord
from studymate.infrastructure.persistence.goal_models import GoalRecord, GoalRevisionRecord
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from tests.integration.catalogue_fixture import subject
from tests.integration.operator.test_reads import operator
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.student_actor import Actor, actor
from tests.integration.test_goals import command, completion, services

pytestmark = pytest.mark.integration
CODEC = FernetOperatorGoalCursorCodec.from_key(b"g" * 32)
RAW_LABEL = " Original raw retained subject "
RAW_TOPIC = " Private retained topic "
RAW_KEY = " Legacy MATCH ß "
RAW_CONTEXT = " Private retained context\n original "


@dataclass(frozen=True, slots=True)
class Goals:
    owner: Actor
    target: Actor
    ended_id: UUID
    active_id: UUID
    subject_id: UUID
    uow: SqlOperatorGoalUnitOfWork

    def roots(self) -> ReadOperatorGoals:
        return ReadOperatorGoals(self.uow, HASHER, FINGERPRINTER, CODEC)

    def history(self) -> ReadOperatorGoalHistory:
        return ReadOperatorGoalHistory(self.uow, HASHER, CODEC)


async def prepared(engine: AsyncEngine) -> Goals:
    target = await actor(engine)
    known = await subject(engine)
    save, close, _ = services(engine)
    first = await save(
        replace(
            command(target),
            content=GoalContent(
                CanonicalSubjectRef(known.id), "First topic", "Original private context", True
            ),
        )
    )
    second = await save(
        replace(command(target, first), content=replace(first.goal.content, topic="Second topic"))
    )
    ended = await close(completion(target, second))
    active = await save(command(target))
    owner = await operator(engine)
    unit = SqlOperatorGoalUnitOfWork(
        async_sessionmaker(engine, expire_on_commit=False), record_operator_audit
    )
    return Goals(owner, target, ended.goal.id, active.goal.id, known.id, unit)


async def seed_goal(session: AsyncSession, owner: UUID, created_at: datetime) -> UUID:
    goal_id = uuid4()
    session.add(
        GoalRecord(
            id=goal_id,
            account_id=owner,
            current_version=1,
            created_at=created_at,
            completed_at=created_at,
        )
    )
    await session.flush()
    session.add(
        GoalRevisionRecord(
            goal_id=goal_id,
            account_id=owner,
            version=1,
            subject_id=None,
            subject_label=RAW_LABEL,
            topic=RAW_TOPIC,
            topic_match_key=RAW_KEY,
            context=RAW_CONTEXT,
            shared_learning=False,
            saved_at=created_at,
            completed_at=created_at,
        )
    )
    await session.flush()
    return goal_id


async def test_raw_goal_history_survives_catalogue_target_deletion_and_clock_regression(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    async with api.uow.sessions.begin() as session:
        root = await session.get(GoalRecord, api.ended_id)
        assert root is not None
        old = root.created_at - timedelta(days=1)
        await session.execute(
            update(GoalRevisionRecord)
            .where(GoalRevisionRecord.goal_id == api.ended_id, GoalRevisionRecord.version == 1)
            .values(
                subject_label=RAW_LABEL,
                topic=RAW_TOPIC,
                topic_match_key=RAW_KEY,
                context=RAW_CONTEXT,
                saved_at=old,
            )
        )
        renamed = "Renamed archived catalogue label"
        await session.execute(
            update(SubjectRecord)
            .where(SubjectRecord.id == api.subject_id)
            .values(
                name=renamed,
                normalized_name=subject_key(renamed),
                archived_at=func.clock_timestamp(),
            )
        )
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == api.target.id)
            .values(banned_at=func.clock_timestamp(), deleted_at=func.clock_timestamp())
        )
    roots = await api.roots()(api.owner.credential, api.target.id, OperatorGoalFilters())
    assert roots is not None
    assert {row.id for row in roots.goals} == {api.active_id, api.ended_id}
    page = await api.history()(api.owner.credential, api.target.id, api.ended_id)
    assert page is not None
    assert tuple(row.version for row in page.revisions) == (3, 2, 1)
    raw = page.revisions[-1]
    assert raw.subject_id == api.subject_id
    assert raw.subject_label == RAW_LABEL
    assert raw.topic == RAW_TOPIC
    assert raw.topic_match_key == RAW_KEY
    assert raw.context == RAW_CONTEXT
    assert raw.saved_at < page.goal.created_at
    assert page.revisions[0].completed_at is not None
    async with api.uow.sessions() as session:
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
        assert all(
            row.action == "read_account" and row.result_ids == [api.target.id] for row in audits
        )
        events = tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        )
        assert {row.operator_audit_id for row in events} == {row.id for row in audits}


async def test_root_filters_future_creation_and_halfopen_boundaries_are_metadata_not_now_gate(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    active = await api.roots()(
        api.owner.credential, api.target.id, OperatorGoalFilters(OperatorGoalState.ACTIVE)
    )
    completed = await api.roots()(
        api.owner.credential, api.target.id, OperatorGoalFilters(OperatorGoalState.COMPLETED)
    )
    assert active is not None
    assert completed is not None
    assert tuple(row.id for row in active.goals) == (api.active_id,)
    assert tuple(row.id for row in completed.goals) == (api.ended_id,)
    async with api.uow.sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        future = now + timedelta(days=1)
        future_id = await seed_goal(session, api.target.id, future)
    listed = await api.roots()(api.owner.credential, api.target.id, OperatorGoalFilters())
    assert listed is not None
    assert listed.goals[0].id == future_id
    assert listed.anchor_goal_id == future_id
    assert listed.observed_at < future
    lower = await api.roots()(
        api.owner.credential, api.target.id, OperatorGoalFilters(created_from=future)
    )
    upper = await api.roots()(
        api.owner.credential, api.target.id, OperatorGoalFilters(created_before=future)
    )
    assert lower is not None
    assert upper is not None
    assert tuple(row.id for row in lower.goals) == (future_id,)
    assert future_id not in {row.id for row in upper.goals}


async def test_empty_account_and_missing_child_have_truthful_account_container_audits(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    empty = await actor(identity_engine)
    page = await api.roots()(api.owner.credential, empty.id, OperatorGoalFilters())
    assert page is not None
    assert page.goals == ()
    assert page.anchor_goal_id is None
    assert await api.history()(api.owner.credential, api.target.id, uuid4()) is None
    other = await actor(identity_engine)
    async with api.uow.sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        foreign = await seed_goal(session, other.id, now)
    assert await api.history()(api.owner.credential, api.target.id, foreign) is None
    missing_account = uuid4()
    assert await api.history()(api.owner.credential, missing_account, api.active_id) is None
    assert await api.roots()(api.owner.credential, missing_account, OperatorGoalFilters()) is None
    async with api.uow.sessions() as session:
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
        for row in audits:
            if row.requested_id == missing_account:
                assert row.outcome == "not_found"
                assert row.result_ids == []
            else:
                assert row.outcome == "read"
                assert row.result_ids == [row.requested_id]
        child_misses = [row for row in audits if row.requested_id == api.target.id]
        assert len(child_misses) == len((foreign, api.active_id))


async def test_goal_history_max_all_revisions_and_owned_source_ignores_current_pointer(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    upper = OPERATOR_GOAL_PAGE_SIZE + 2
    async with api.uow.sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        for version in range(2, upper + 1):
            session.add(
                GoalRevisionRecord(
                    goal_id=api.active_id,
                    account_id=api.target.id,
                    version=version,
                    subject_id=None,
                    subject_label=RAW_LABEL,
                    topic=RAW_TOPIC,
                    topic_match_key=RAW_KEY,
                    context=RAW_CONTEXT,
                    shared_learning=True,
                    saved_at=now,
                    completed_at=None,
                )
            )
    first = await api.history()(api.owner.credential, api.target.id, api.active_id)
    assert first is not None
    assert first.anchor_version == upper
    assert first.goal.current_version < first.anchor_version
    assert len(first.revisions) == OPERATOR_GOAL_PAGE_SIZE
    assert first.revisions[0].subject_id is None
    assert first.revisions[0].topic_match_key == RAW_KEY
    assert first.next_cursor is not None
    async with api.uow.sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        session.add(
            GoalRevisionRecord(
                goal_id=api.active_id,
                account_id=api.target.id,
                version=upper + 1,
                subject_id=None,
                subject_label=RAW_LABEL,
                topic=None,
                topic_match_key=None,
                context=None,
                shared_learning=False,
                saved_at=now,
                completed_at=None,
            )
        )
    second = await api.history()(
        api.owner.credential, api.target.id, api.active_id, first.next_cursor
    )
    assert second is not None
    assert tuple(row.version for row in second.revisions) == (2, 1)
    assert second.anchor_version == upper
    assert second.next_cursor is None
    refresh = await api.history()(api.owner.credential, api.target.id, api.active_id)
    assert refresh is not None
    assert refresh.anchor_version == upper + 1
    assert refresh.revisions[0].topic is None


async def test_physical_late_commit_root_is_not_promised_by_created_metadata_keyset(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    async with api.uow.sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        ids = {
            await seed_goal(session, api.target.id, now - timedelta(minutes=index))
            for index in range(1, OPERATOR_GOAL_PAGE_SIZE + 3)
        }
    entered, release = asyncio.Event(), asyncio.Event()
    late_id: UUID | None = None

    async def late_commit() -> None:
        nonlocal late_id
        async with api.uow.sessions.begin() as session:
            late_id = await seed_goal(session, api.target.id, now - timedelta(minutes=2, seconds=1))
            entered.set()
            await release.wait()

    task = asyncio.create_task(late_commit())
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        first = await api.roots()(api.owner.credential, api.target.id, OperatorGoalFilters())
        assert first is not None
        assert first.next_cursor is not None
        assert late_id not in {row.id for row in first.goals}
        release.set()
        await asyncio.wait_for(task, timeout=5)
        second = await api.roots()(
            api.owner.credential, api.target.id, OperatorGoalFilters(), first.next_cursor
        )
        assert second is not None
        assert second.next_cursor is None
        combined = {row.id for row in first.goals + second.goals}
        assert combined == ids | {api.active_id, api.ended_id}
        assert late_id not in combined
        refreshed = await api.roots()(api.owner.credential, api.target.id, OperatorGoalFilters())
        assert refreshed is not None
        assert late_id in {row.id for row in refreshed.goals}
    finally:
        release.set()
        await task


async def test_current_metadata_completion_changes_are_fresh_on_refresh_not_old_snapshot(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    before = await api.roots()(
        api.owner.credential, api.target.id, OperatorGoalFilters(OperatorGoalState.ACTIVE)
    )
    assert before is not None
    assert tuple(row.id for row in before.goals) == (api.active_id,)
    _, close, read = services(identity_engine)
    current = await read(api.target.credential)
    assert current is not None
    await close(completion(api.target, current))
    active = await api.roots()(
        api.owner.credential, api.target.id, OperatorGoalFilters(OperatorGoalState.ACTIVE)
    )
    ended = await api.roots()(
        api.owner.credential, api.target.id, OperatorGoalFilters(OperatorGoalState.COMPLETED)
    )
    assert active is not None
    assert active.goals == ()
    assert ended is not None
    assert {row.id for row in ended.goals} == {api.active_id, api.ended_id}
    assert before.goals[0].completed_at is None


async def test_explicit_current_operator_precedes_root_and_revision_sql(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    async with api.uow.sessions() as session:
        with pytest.raises(RuntimeError, match="operator"):
            await SqlOperatorGoalTransaction(session, record_operator_audit).goal_account(
                api.target.id
            )
    with pytest.raises(OperatorAccessDeniedError):
        await api.roots()(api.target.credential, api.target.id, OperatorGoalFilters())
    revoked = await operator(identity_engine, active=False)
    with pytest.raises(OperatorAccessDeniedError):
        await api.history()(revoked.credential, api.target.id, api.active_id)
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))


@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize("reading_history", [False, True])
async def test_goal_inspection_canonical_failure_or_cancel_rolls_back_without_data(
    identity_engine: AsyncEngine, cancel: bool, reading_history: bool
) -> None:
    api = await prepared(identity_engine)

    async def failing(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        if cancel:
            raise asyncio.CancelledError
        raise RuntimeError("Synthetic goal inspection canonical failure")

    unit = SqlOperatorGoalUnitOfWork(api.uow.sessions, failing)
    operation = (
        ReadOperatorGoalHistory(unit, HASHER, CODEC)(
            api.owner.credential, api.target.id, api.active_id
        )
        if reading_history
        else ReadOperatorGoals(unit, HASHER, FINGERPRINTER, CODEC)(
            api.owner.credential, api.target.id, OperatorGoalFilters()
        )
    )
    with pytest.raises(asyncio.CancelledError if cancel else RuntimeError):
        await operation
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
        assert not tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        )
    assert await api.history()(api.owner.credential, api.target.id, api.active_id) is not None


@pytest.mark.parametrize("reading_history", [False, True])
async def test_goal_final_session_expiry_after_canonical_prevents_private_response(
    identity_engine: AsyncEngine, reading_history: bool
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

    unit = SqlOperatorGoalUnitOfWork(api.uow.sessions, expired)
    operation = (
        ReadOperatorGoalHistory(unit, HASHER, CODEC)(
            api.owner.credential, api.target.id, api.active_id
        )
        if reading_history
        else ReadOperatorGoals(unit, HASHER, FINGERPRINTER, CODEC)(
            api.owner.credential, api.target.id, OperatorGoalFilters()
        )
    )
    with pytest.raises(UnauthenticatedError):
        await operation
    assert entered
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))


async def test_hidden_goal_sources_remain_privileged_without_profile_disclosure_grant(
    identity_engine: AsyncEngine,
) -> None:
    from tests.integration.profile_lifecycle_fixture import (
        activated,
    )
    from tests.integration.profile_lifecycle_fixture import (
        command as hide_command,
    )
    from tests.integration.profile_lifecycle_fixture import (
        services as visibility_services,
    )

    target = await activated(identity_engine)
    save, _, read = services(identity_engine)
    current = await read(target.credential)
    if current is None:
        current = await save(command(target))
    visibility, _ = visibility_services(identity_engine)
    await visibility(hide_command(target))
    owner = await operator(identity_engine)
    unit = SqlOperatorGoalUnitOfWork(
        async_sessionmaker(identity_engine, expire_on_commit=False), record_operator_audit
    )
    roots = await ReadOperatorGoals(unit, HASHER, FINGERPRINTER, CODEC)(
        owner.credential, target.id, OperatorGoalFilters()
    )
    history = await ReadOperatorGoalHistory(unit, HASHER, CODEC)(
        owner.credential, target.id, current.goal.id
    )
    assert roots is not None
    assert current.goal.id in {row.id for row in roots.goals}
    assert history is not None
    assert history.goal.account_id == target.id
