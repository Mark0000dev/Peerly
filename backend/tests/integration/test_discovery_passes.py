import asyncio
from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import studymate.infrastructure.persistence.discovery_passes as pass_module
import studymate.infrastructure.persistence.product_events as event_module
from studymate.application.discovery.passes import (
    ChangePassCommand,
    ChangePrivatePass,
    PassUndoUnavailableError,
    PrivatePassConflictError,
)
from studymate.application.idempotency import IntentKey
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.discovery_context import discovery_context
from studymate.domain.discovery_passes import PrivatePassRevision
from studymate.infrastructure.observability.origin import ExecutionOrigin
from studymate.infrastructure.persistence.discovery_decisions import advance_discovery_decision
from studymate.infrastructure.persistence.discovery_pass_models import (
    DiscoveryContextRecord,
    DiscoveryDecisionHeadRecord,
    PrivatePassIntentRecord,
    PrivatePassRevisionRecord,
)
from studymate.infrastructure.persistence.discovery_passes import (
    SqlPrivatePassUnitOfWork,
)
from studymate.infrastructure.persistence.goal_models import GoalRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.discovery_fixture import discovery_actors
from tests.integration.migrations import run_revision_step

pytestmark = pytest.mark.integration


def service(engine: AsyncEngine) -> ChangePrivatePass:
    return ChangePrivatePass(
        SqlPrivatePassUnitOfWork(async_sessionmaker(engine, expire_on_commit=False)),
        Sha256SessionHasher(),
        HmacIntentFingerprinter(bytes(range(32))),
    )


async def submission(engine: AsyncEngine) -> ChangePassCommand:
    setup = await discovery_actors(engine)
    context = discovery_context(setup.viewer.id, DiscoveryMode.FIND_HELP, setup.goal.goal, None)
    assert context is not None
    return ChangePassCommand(
        setup.viewer.credential, context.scope, setup.target.id, True, 0, IntentKey(str(uuid4()))
    )


async def submission_owner(engine: AsyncEngine, send: ChangePassCommand) -> UUID:
    assert send.context.goal_id is not None
    async with async_sessionmaker(engine)() as session:
        return (
            await session.execute(
                select(GoalRecord.account_id).where(GoalRecord.id == send.context.goal_id)
            )
        ).scalar_one()


async def test_pass_history_replay_and_undo_use_real_immutable_sources(
    identity_engine: AsyncEngine,
) -> None:
    send = await submission(identity_engine)
    change = service(identity_engine)
    first = await change(send)
    reconsidered = await change(
        replace(
            send,
            passed=False,
            undo=True,
            expected_version=first.version,
            intent_key=IntentKey(str(uuid4())),
        )
    )
    assert not reconsidered.passed
    assert await change(send) == first
    async with async_sessionmaker(identity_engine)() as session:
        assert await session.scalar(select(func.count()).select_from(DiscoveryContextRecord)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(PrivatePassRevisionRecord))
            == reconsidered.version
        )
        assert (
            await session.scalar(select(func.count()).select_from(PrivatePassIntentRecord))
            == reconsidered.version
        )
        head = await session.get(
            DiscoveryDecisionHeadRecord, await submission_owner(identity_engine, send)
        )
        assert head is not None
        assert head.last_sequence == reconsidered.decision_sequence


async def test_parallel_same_intent_is_once_only(identity_engine: AsyncEngine) -> None:
    send = await submission(identity_engine)
    change = service(identity_engine)
    results = await asyncio.wait_for(asyncio.gather(change(send), change(send)), timeout=10)
    assert results[0] == results[1]
    async with async_sessionmaker(identity_engine)() as session:
        assert (
            await session.scalar(select(func.count()).select_from(PrivatePassRevisionRecord)) == 1
        )
        assert await session.scalar(select(func.count()).select_from(PrivatePassIntentRecord)) == 1


async def test_parallel_different_intents_recheck_actual_version_under_account_locks(
    identity_engine: AsyncEngine,
) -> None:
    send = await submission(identity_engine)
    change = service(identity_engine)
    outcomes = await asyncio.wait_for(
        asyncio.gather(
            change(send),
            change(replace(send, intent_key=IntentKey(str(uuid4())))),
            return_exceptions=True,
        ),
        timeout=10,
    )
    assert sum(isinstance(value, PrivatePassConflictError) for value in outcomes) == 1
    async with async_sessionmaker(identity_engine)() as session:
        assert (
            await session.scalar(select(func.count()).select_from(PrivatePassRevisionRecord)) == 1
        )


async def test_actual_later_committed_decision_ends_undo_without_deleting_pass(
    identity_engine: AsyncEngine,
) -> None:
    send = await submission(identity_engine)
    change = service(identity_engine)
    first = await change(send)
    uow = SqlPrivatePassUnitOfWork(async_sessionmaker(identity_engine, expire_on_commit=False))
    async with uow.transaction(send.target_id) as transaction:
        identity = await transaction.lock_identity(
            await Sha256SessionHasher().digest(send.credential)
        )
        assert identity is not None
        # Exercise the shared real helper in the same account-locked SQL transaction.
        await advance_discovery_decision(transaction.session, identity.session.account_id)
    undo = replace(
        send,
        passed=False,
        undo=True,
        expected_version=first.version,
        intent_key=IntentKey(str(uuid4())),
    )
    with pytest.raises(PassUndoUnavailableError):
        await change(undo)
    assert not (await change(replace(undo, undo=False))).passed


async def test_foreign_goal_cannot_be_attached_to_private_context(
    identity_engine: AsyncEngine,
) -> None:
    send = await submission(identity_engine)
    sessions = async_sessionmaker(identity_engine)
    async with sessions() as session:
        foreign = await session.scalar(
            select(GoalRecord).where(GoalRecord.account_id == send.target_id)
        )
        assert foreign is not None
        foreign_id, foreign_version = foreign.id, foreign.current_version
    with pytest.raises(IntegrityError):
        async with sessions.begin() as session:
            session.add(
                DiscoveryContextRecord(
                    id=uuid4(),
                    account_id=await submission_owner(identity_engine, send),
                    mode="find_help",
                    goal_id=foreign_id,
                    goal_version=foreign_version,
                    help_version=None,
                )
            )


async def test_private_history_cannot_be_downgraded_away(identity_engine: AsyncEngine) -> None:
    send = await submission(identity_engine)
    first = await service(identity_engine)(send)

    with pytest.raises(RuntimeError, match="retained private discovery"):
        async with identity_engine.begin() as connection:
            await connection.run_sync(
                run_revision_step, "0025_discovery_private_passes", "downgrade"
            )
    assert await service(identity_engine)(send) == first


async def test_rolled_back_other_decision_does_not_end_latest_pass_undo(
    identity_engine: AsyncEngine,
) -> None:
    send = await submission(identity_engine)
    change = service(identity_engine)
    first = await change(send)
    uow = SqlPrivatePassUnitOfWork(async_sessionmaker(identity_engine, expire_on_commit=False))

    async def aborted_decision() -> None:
        async with uow.transaction(send.target_id) as transaction:
            identity = await transaction.lock_identity(
                await Sha256SessionHasher().digest(send.credential)
            )
            assert identity is not None
            await advance_discovery_decision(transaction.session, identity.session.account_id)
            raise RuntimeError("abort decision")

    with pytest.raises(RuntimeError, match="abort decision"):
        await aborted_decision()
    undo = replace(
        send,
        passed=False,
        undo=True,
        expected_version=first.version,
        intent_key=IntentKey(str(uuid4())),
    )
    assert not (await change(undo)).passed


async def test_canonical_private_pass_events_are_once_only_and_correlated(
    identity_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    send = await submission(identity_engine)
    origin = ExecutionOrigin(uuid4(), uuid4(), "a" * 32, "b" * 16)
    monkeypatch.setattr(event_module, "current_origin", lambda: origin)
    change = service(identity_engine)
    first = await change(send)
    reconsidered = await change(
        replace(
            send, passed=False, expected_version=first.version, intent_key=IntentKey(str(uuid4()))
        )
    )
    assert await change(send) == first
    async with async_sessionmaker(identity_engine)() as session:
        events = (
            await session.scalars(
                select(ProductEventRecord)
                .where(ProductEventRecord.kind == "discovery.pass_changed")
                .order_by(ProductEventRecord.private_pass_version)
            )
        ).all()
        assert [row.private_passed for row in events] == [True, False]
        assert [row.private_pass_version for row in events] == [first.version, reconsidered.version]
        for row in events:
            assert row.account_id == await submission_owner(identity_engine, send)
            assert row.private_pass_id == first.id
            assert row.request_id == origin.request_id
            assert row.action_id == origin.action_id
            assert row.trace_id == origin.trace_id
            assert row.span_id == origin.span_id
            assert row.goal_id is None
            assert row.subject_id is None


@pytest.mark.parametrize("mixed_family", [False, True])
async def test_canonical_pass_event_cannot_contradict_source_or_mix_families(
    identity_engine: AsyncEngine, mixed_family: bool
) -> None:
    send = await submission(identity_engine)
    first = await service(identity_engine)(send)
    with pytest.raises(IntegrityError):
        async with async_sessionmaker(identity_engine).begin() as session:
            session.add(
                ProductEventRecord(
                    id=uuid4(),
                    account_id=await submission_owner(identity_engine, send),
                    kind="discovery.pass_changed",
                    occurrence_key="contradiction",
                    schema_version=1,
                    occurred_at=first.changed_at,
                    private_pass_id=first.id,
                    private_pass_version=first.version,
                    private_passed=mixed_family,
                    goal_id=send.context.goal_id if mixed_family else None,
                    goal_version=send.context.goal_version if mixed_family else None,
                )
            )


async def test_canonical_failure_rolls_back_pass_context_head_and_intent(
    identity_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    send = await submission(identity_engine)
    original = event_module.record_private_pass_event

    async def fail_after_event(session: AsyncSession, revision: PrivatePassRevision) -> None:
        await original(session, revision)
        raise RuntimeError("controlled post-event failure")

    monkeypatch.setattr(pass_module, "record_private_pass_event", fail_after_event)
    with pytest.raises(RuntimeError, match="controlled post-event failure"):
        await service(identity_engine)(send)
    async with async_sessionmaker(identity_engine)() as session:
        assert await session.scalar(select(func.count()).select_from(DiscoveryContextRecord)) == 0
        assert (
            await session.scalar(select(func.count()).select_from(DiscoveryDecisionHeadRecord)) == 0
        )
        assert (
            await session.scalar(select(func.count()).select_from(PrivatePassRevisionRecord)) == 0
        )
        assert await session.scalar(select(func.count()).select_from(PrivatePassIntentRecord)) == 0
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProductEventRecord)
                .where(ProductEventRecord.kind == "discovery.pass_changed")
            )
            == 0
        )
