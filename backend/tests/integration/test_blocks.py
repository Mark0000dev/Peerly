import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.safety.blocks import (
    BlockTargetUnavailableError,
    BlockVersionConflictError,
    ChangeBlockCommand,
    ChangeOwnBlock,
)
from studymate.domain.relationships import AccountPair, BlockRevision, pair_is_blocked
from studymate.infrastructure.persistence.block_models import (
    BlockIntentRecord,
    BlockRecord,
    BlockRevisionRecord,
    RelationshipRecord,
)
from studymate.infrastructure.persistence.blocks import SqlBlockTransaction, SqlBlockUnitOfWork
from studymate.infrastructure.persistence.goal_models import GoalRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.report_models import ProfileAccessRecord
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.migrations import run_revision_step
from tests.integration.safety_fixture import prepared
from tests.integration.student_actor import Actor

pytestmark = pytest.mark.integration


def service(engine: AsyncEngine) -> ChangeOwnBlock:
    return ChangeOwnBlock(
        SqlBlockUnitOfWork(async_sessionmaker(engine, expire_on_commit=False)),
        Sha256SessionHasher(),
        HmacIntentFingerprinter(bytes(range(32))),
    )


def command(owner: Actor, target: Actor, context_id: UUID) -> ChangeBlockCommand:
    return ChangeBlockCommand(
        owner.credential, target.id, True, 0, IntentKey(str(uuid4())), context_id
    )


async def reverse_context(engine: AsyncEngine, viewer: Actor, target: Actor) -> UUID:
    async with async_sessionmaker(engine).begin() as session:
        goal = await session.scalar(select(GoalRecord).where(GoalRecord.account_id == target.id))
        assert goal is not None
        context_id = uuid4()
        session.add(
            ProfileAccessRecord(
                id=context_id,
                viewer_id=viewer.id,
                target_id=target.id,
                profile_version=1,
                photo_version=1,
                goal_id=goal.id,
                goal_version=goal.current_version,
                help_version=None,
                issued_at=datetime.now(UTC),
            )
        )
    return context_id


async def test_block_retains_original_replay_and_unblock_history(
    identity_engine: AsyncEngine,
) -> None:
    viewer, target, context = await prepared(identity_engine)
    change = service(identity_engine)
    intent = command(viewer, target, context.id)
    blocked = await change(intent)
    assert blocked.blocked
    assert await change(intent) == blocked
    with pytest.raises(IdempotencyConflictError):
        await change(replace(intent, blocked=False))
    with pytest.raises(BlockTargetUnavailableError):
        await change(
            replace(
                intent,
                blocked=False,
                expected_version=1,
                intent_key=IntentKey(str(uuid4())),
                context_id=uuid4(),
            )
        )
    unblocked = await change(
        replace(
            intent,
            blocked=False,
            expected_version=1,
            intent_key=IntentKey(str(uuid4())),
            context_id=None,
        )
    )
    assert not unblocked.blocked
    assert unblocked.version == blocked.version + 1
    assert await change(intent) == blocked
    async with async_sessionmaker(identity_engine)() as session:
        current = await SqlBlockTransaction(session, target.id).current_own_block(
            viewer.id, target.id
        )
        assert current.own is not None
        assert not current.own.blocked
        assert current.own.version == unblocked.version
        original = await session.get(BlockIntentRecord, (viewer.id, intent.intent_key.value))
        assert original is not None
        assert original.context_id == context.id
        assert await session.scalar(select(func.count()).select_from(RelationshipRecord)) == 1
        assert tuple(
            await session.scalars(
                select(BlockRevisionRecord.version).order_by(BlockRevisionRecord.version)
            )
        ) == (blocked.version, unblocked.version)


async def test_reciprocal_block_race_has_one_pair_and_independent_unblock(
    identity_engine: AsyncEngine,
) -> None:
    viewer, target, context = await prepared(identity_engine)
    reverse_id = await reverse_context(identity_engine, target, viewer)
    change = service(identity_engine)
    first, second = await asyncio.wait_for(
        asyncio.gather(
            change(command(viewer, target, context.id)), change(command(target, viewer, reverse_id))
        ),
        timeout=5,
    )
    assert first.blocked
    assert second.blocked
    await change(
        ChangeBlockCommand(viewer.credential, target.id, False, 1, IntentKey(str(uuid4())))
    )
    async with async_sessionmaker(identity_engine)() as session:
        transaction = SqlBlockTransaction(session, target.id)
        own = await transaction.current_own_block(viewer.id, target.id)
        other = await transaction.current_own_block(target.id, viewer.id)
        assert own.relationship_id == other.relationship_id
        assert own.own is not None
        assert not own.own.blocked
        assert other.own is not None
        assert other.own.blocked
        assert pair_is_blocked(own.own, other.own)
        assert await session.scalar(select(func.count()).select_from(RelationshipRecord)) == 1


async def test_absent_unblock_creates_no_dummy_pair_or_block(identity_engine: AsyncEngine) -> None:
    viewer, target, context = await prepared(identity_engine)
    change = service(identity_engine)
    intent = replace(command(viewer, target, context.id), blocked=False)
    absent = await change(intent)
    assert absent.version == 0
    assert not absent.blocked
    assert absent.changed_at is None
    async with async_sessionmaker(identity_engine)() as session:
        assert await session.scalar(select(func.count()).select_from(RelationshipRecord)) == 0
        assert await session.scalar(select(func.count()).select_from(BlockRevisionRecord)) == 0
        assert await session.scalar(select(func.count()).select_from(BlockIntentRecord)) == 1
    await change(command(viewer, target, context.id))
    assert await change(intent) == absent


async def test_foreign_context_cannot_create_block(identity_engine: AsyncEngine) -> None:
    viewer, target, context = await prepared(identity_engine)
    with pytest.raises(BlockTargetUnavailableError):
        await service(identity_engine)(command(target, viewer, context.id))
    async with async_sessionmaker(identity_engine)() as session:
        assert await session.scalar(select(func.count()).select_from(RelationshipRecord)) == 0


async def test_competing_block_intents_enforce_own_version(identity_engine: AsyncEngine) -> None:
    viewer, target, context = await prepared(identity_engine)
    change = service(identity_engine)

    async def attempt() -> bool:
        try:
            await change(command(viewer, target, context.id))
        except BlockVersionConflictError:
            return False
        return True

    assert sorted(await asyncio.gather(attempt(), attempt())) == [False, True]


async def test_database_enforces_pair_and_directional_participants(
    identity_engine: AsyncEngine,
) -> None:
    viewer, target, _ = await prepared(identity_engine)
    pair = AccountPair.between(viewer.id, target.id)
    sessions = async_sessionmaker(identity_engine)
    relationship_id = uuid4()
    async with sessions.begin() as session:
        session.add(RelationshipRecord(id=relationship_id, low_id=pair.low, high_id=pair.high))
    with pytest.raises(IntegrityError):
        async with sessions.begin() as session:
            session.add(RelationshipRecord(id=uuid4(), low_id=pair.high, high_id=pair.low))
    with pytest.raises(IntegrityError):
        async with sessions.begin() as session:
            session.add(
                BlockRevisionRecord(
                    relationship_id=relationship_id,
                    blocker_id=uuid4(),
                    target_id=target.id,
                    version=1,
                    low_id=pair.low,
                    high_id=pair.high,
                    blocked=True,
                    changed_at=datetime.now(UTC),
                )
            )


async def test_failed_block_write_rolls_back_pair_and_revision(
    identity_engine: AsyncEngine,
) -> None:
    viewer, target, _ = await prepared(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    revision = BlockRevision(
        uuid4(), AccountPair.between(viewer.id, target.id), viewer.id, 1, True, datetime.now(UTC)
    )

    async def failed_write() -> None:
        async with SqlBlockUnitOfWork(sessions).transaction(target.id) as transaction:
            await transaction.save_block(revision)
            raise RuntimeError("controlled rollback")

    with pytest.raises(RuntimeError, match="controlled"):
        await failed_write()
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(RelationshipRecord)) == 0
        assert await session.scalar(select(func.count()).select_from(BlockRecord)) == 0

        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProductEventRecord)
                .where(ProductEventRecord.kind == "block.changed")
            )
            == 0
        )


async def test_peer_cannot_remove_other_direction_by_unblocking_absent_own_state(
    identity_engine: AsyncEngine,
) -> None:
    viewer, target, context = await prepared(identity_engine)
    reverse_id = await reverse_context(identity_engine, target, viewer)
    change = service(identity_engine)
    await change(command(viewer, target, context.id))
    own_absent = await change(replace(command(target, viewer, reverse_id), blocked=False))
    assert own_absent.version == 0
    assert not own_absent.blocked
    async with async_sessionmaker(identity_engine)() as session:
        other = await SqlBlockTransaction(session, target.id).current_own_block(
            viewer.id, target.id
        )
        assert other.own is not None
        assert other.own.blocked
        assert await session.scalar(select(func.count()).select_from(BlockRecord)) == 1


async def test_relationship_downgrade_refuses_retained_pair_history(
    identity_engine: AsyncEngine,
) -> None:

    viewer, target, context = await prepared(identity_engine)
    await service(identity_engine)(command(viewer, target, context.id))
    with pytest.raises(RuntimeError, match=r"retained.*history"):
        async with identity_engine.begin() as connection:
            await connection.run_sync(run_revision_step, "0021_directional_blocks", "downgrade")
    async with async_sessionmaker(identity_engine)() as session:
        assert await session.scalar(select(func.count()).select_from(RelationshipRecord)) == 1
        assert await session.scalar(select(func.count()).select_from(BlockRevisionRecord)) == 1
