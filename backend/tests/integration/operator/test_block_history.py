from dataclasses import replace
from datetime import datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.operator.block_history import ReadOperatorBlockHistory
from studymate.application.safety.blocks import ChangeBlockCommand
from studymate.domain.operator.audit import OperatorAudit
from studymate.domain.operator.block_history import OPERATOR_BLOCK_HISTORY_PAGE_SIZE
from studymate.infrastructure.operator.block_history_cursors import (
    FernetOperatorBlockHistoryCursorCodec,
)
from studymate.infrastructure.operator.block_history_transactions import (
    SqlOperatorBlockHistoryUnitOfWork,
)
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.persistence.block_models import (
    BlockRecord,
    BlockRevisionRecord,
    RelationshipRecord,
)
from studymate.infrastructure.persistence.conversation_models import ConversationRecord
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from tests.integration.operator.test_reads import operator
from tests.integration.requests.fixture import HASHER
from tests.integration.safety_fixture import prepared
from tests.integration.student_actor import actor
from tests.integration.test_blocks import command, reverse_context, service
from tests.integration.test_message_commands import chat

pytestmark = pytest.mark.integration
CODEC = FernetOperatorBlockHistoryCursorCodec.from_key(b"b" * 32)


def reader(engine: AsyncEngine) -> ReadOperatorBlockHistory:
    return ReadOperatorBlockHistory(
        SqlOperatorBlockHistoryUnitOfWork(
            async_sessionmaker(engine, expire_on_commit=False), record_operator_audit
        ),
        HASHER,
        CODEC,
    )


async def relationship_id(engine: AsyncEngine, account_id: UUID) -> UUID:
    async with async_sessionmaker(engine)() as session:
        id_ = await session.scalar(
            select(RelationshipRecord.id).where(
                (RelationshipRecord.low_id == account_id)
                | (RelationshipRecord.high_id == account_id)
            )
        )
        assert id_ is not None
        return id_


async def test_real_relationship_without_block_rows_has_no_synthetic_unblocked_heads(
    identity_engine: AsyncEngine,
) -> None:
    context = await chat(identity_engine)
    viewer = await operator(identity_engine)
    relation = await relationship_id(identity_engine, context.sender.id)
    page = await reader(identity_engine)(viewer.credential, context.sender.id, relation)
    assert page is not None
    assert page.current_heads == ()
    assert page.revisions == ()
    assert page.anchors.low_version == 0
    assert page.anchors.high_version == 0
    assert page.next_cursor is None


async def test_block_created_pair_is_not_a_chat_and_read_does_not_create_one(
    identity_engine: AsyncEngine,
) -> None:
    first, second, context = await prepared(identity_engine)
    await service(identity_engine)(command(first, second, context.id))
    viewer = await operator(identity_engine)
    relation = await relationship_id(identity_engine, first.id)
    page = await reader(identity_engine)(viewer.credential, first.id, relation)
    assert page is not None
    assert len(page.current_heads) == 1
    assert page.current_heads[0].blocker_id == first.id
    assert page.current_heads[0].target_id == second.id
    async with async_sessionmaker(identity_engine)() as session:
        assert tuple(await session.scalars(select(ConversationRecord))) == ()
        assert len(tuple(await session.scalars(select(BlockRevisionRecord)))) == 1


async def test_actual_reciprocal_history_retains_direction_after_subject_ban_and_delete(
    identity_engine: AsyncEngine,
) -> None:
    first, second, context = await prepared(identity_engine)
    reverse = await reverse_context(identity_engine, second, first)
    change = service(identity_engine)
    original = command(first, second, context.id)
    await change(original)
    await change(command(second, first, reverse))
    await change(
        replace(
            original,
            blocked=False,
            expected_version=1,
            intent_key=IntentKey(str(uuid4())),
            context_id=None,
        )
    )
    viewer = await operator(identity_engine)
    relation = await relationship_id(identity_engine, first.id)
    async with async_sessionmaker(identity_engine).begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id.in_((first.id, second.id)))
            .values(deleted_at=func.clock_timestamp(), banned_at=func.clock_timestamp())
        )
    page = await reader(identity_engine)(viewer.credential, first.id, relation)
    assert page is not None
    heads = {source.blocker_id: source for source in page.current_heads}
    assert heads[first.id].blocked is False
    assert heads[second.id].blocked is True
    assert heads[first.id].target_id == second.id
    assert heads[second.id].target_id == first.id
    assert sorted((row.blocker_id, row.version) for row in page.revisions) == sorted(
        ((first.id, 1), (first.id, 2), (second.id, 1))
    )
    async with async_sessionmaker(identity_engine)() as session:
        audit = (await session.scalars(select(OperatorAuditRecord))).one()
        assert audit.action == "read_account"
        assert audit.requested_id == first.id
        assert audit.result_ids == [first.id]
        event = (
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        ).one()
        assert event.operator_audit_id == audit.id


async def test_missing_or_foreign_pair_keeps_existing_account_container_read_audit(
    identity_engine: AsyncEngine,
) -> None:
    first, second, context = await prepared(identity_engine)
    await service(identity_engine)(command(first, second, context.id))
    viewer, other = await operator(identity_engine), await actor(identity_engine)
    relation = await relationship_id(identity_engine, first.id)
    read = reader(identity_engine)
    assert await read(viewer.credential, other.id, relation) is None
    assert await read(viewer.credential, first.id, uuid4()) is None
    missing = uuid4()
    assert await read(viewer.credential, missing, relation) is None
    async with async_sessionmaker(identity_engine)() as session:
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
        for source in audits:
            if source.requested_id == missing:
                assert source.outcome == "not_found"
                assert source.result_ids == []
            else:
                assert source.outcome == "read"
                assert source.result_ids == [source.requested_id]


async def test_real_tied_timestamp_keyset_anchors_both_directions_independently(
    identity_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, second, context = await prepared(identity_engine)
    reverse = await reverse_context(identity_engine, second, first)
    viewer = await operator(identity_engine)
    async with async_sessionmaker(identity_engine)() as session:
        at = await SqlIdentityTransaction(session).now()

    async def clock(_transaction: SqlIdentityTransaction) -> datetime:
        return at

    monkeypatch.setattr(SqlIdentityTransaction, "now", clock)
    many, few = (first, second) if first.id.int > second.id.int else (second, first)
    many_context = context.id if many.id == first.id else reverse
    few_context = context.id if few.id == first.id else reverse
    change = service(identity_engine)
    count = OPERATOR_BLOCK_HISTORY_PAGE_SIZE + 2
    for version in range(count):
        await change(
            ChangeBlockCommand(
                many.credential,
                few.id,
                version % 2 == 0,
                version,
                IntentKey(str(uuid4())),
                many_context if version == 0 else None,
            )
        )
    await change(command(few, many, few_context))
    await change(ChangeBlockCommand(few.credential, many.id, False, 1, IntentKey(str(uuid4()))))
    relation = await relationship_id(identity_engine, first.id)
    read = reader(identity_engine)
    initial = await read(viewer.credential, first.id, relation)
    assert initial is not None
    assert len(initial.revisions) == OPERATOR_BLOCK_HISTORY_PAGE_SIZE
    assert initial.next_cursor is not None
    assert initial.anchors.for_blocker(initial.pair, many.id) == count
    await change(ChangeBlockCommand(many.credential, few.id, True, count, IntentKey(str(uuid4()))))
    await change(ChangeBlockCommand(few.credential, many.id, True, 2, IntentKey(str(uuid4()))))
    tail = await read(viewer.credential, first.id, relation, initial.next_cursor)
    assert tail is not None
    assert {(row.blocker_id, row.version) for row in tail.revisions} == {
        (many.id, 2),
        (many.id, 1),
        (few.id, 2),
        (few.id, 1),
    }
    assert tail.anchors == initial.anchors
    assert tail.next_cursor is None
    heads = {row.blocker_id: row for row in tail.current_heads}
    assert heads[many.id].version == count + 1
    assert heads[few.id].version == initial.anchors.low_version + 1


async def fail_inspection(session: AsyncSession, audit: OperatorAudit) -> None:
    await record_operator_audit(session, audit)
    raise RuntimeError("synthetic block-history inspection failure")


async def test_canonical_inspection_failure_rolls_back_audit_without_changing_blocks(
    identity_engine: AsyncEngine,
) -> None:
    first, second, context = await prepared(identity_engine)
    await service(identity_engine)(command(first, second, context.id))
    viewer = await operator(identity_engine)
    relation = await relationship_id(identity_engine, first.id)
    unit = SqlOperatorBlockHistoryUnitOfWork(
        async_sessionmaker(identity_engine, expire_on_commit=False), fail_inspection
    )
    with pytest.raises(RuntimeError, match="synthetic block-history inspection failure"):
        await ReadOperatorBlockHistory(unit, HASHER, CODEC)(viewer.credential, first.id, relation)
    async with unit.sessions() as session:
        assert tuple(await session.scalars(select(OperatorAuditRecord))) == ()
        assert (
            tuple(
                await session.scalars(
                    select(ProductEventRecord).where(
                        ProductEventRecord.kind == "operator.inspected"
                    )
                )
            )
            == ()
        )
        assert (await session.scalars(select(BlockRecord))).one().current_version == 1
