import asyncio
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.access_history import ReadOperatorAccessHistory
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.cursors import InvalidOperatorCursorError
from studymate.domain.operator.access_history import OPERATOR_ACCESS_HISTORY_PAGE_SIZE
from studymate.domain.operator.audit import OperatorAudit
from studymate.infrastructure.operator.access_history_cursors import (
    FernetOperatorAccessHistoryCursorCodec,
)
from studymate.infrastructure.operator.access_history_transactions import (
    SqlOperatorAccessHistoryUnitOfWork,
)
from studymate.infrastructure.operator.models import (
    OperatorAccessRecord,
    OperatorAccessRevisionRecord,
    OperatorAuditRecord,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.operator.test_reads import operator
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration
CODEC = FernetOperatorAccessHistoryCursorCodec.from_key(b"a" * 32)
TAIL_SIZE = 2
RETAINED_HEAD = 4


def reader(engine: AsyncEngine) -> ReadOperatorAccessHistory:
    return ReadOperatorAccessHistory(
        SqlOperatorAccessHistoryUnitOfWork(
            async_sessionmaker(engine, expire_on_commit=False), record_operator_audit
        ),
        Sha256SessionHasher(),
        CODEC,
    )


async def seed_revisions(
    engine: AsyncEngine, target_id: UUID, grantor_id: UUID, count: int
) -> None:
    async with async_sessionmaker(engine).begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        root = await session.get(OperatorAccessRecord, target_id)
        assert root is not None
        for version in range(2, count + 1):
            session.add(
                OperatorAccessRevisionRecord(
                    account_id=target_id,
                    version=version,
                    active=version % 2 == 1,
                    changed_at=now - timedelta(days=version),
                    changed_by_id=grantor_id,
                    http_request_id=uuid4(),
                    action_id=uuid4(),
                    trace_id="1" * 32,
                    span_id="2" * 16,
                )
            )
        root.current_version = count


async def test_retained_unused_revoked_grants_preserve_exact_source_and_legacy_nulls(
    identity_engine: AsyncEngine,
) -> None:
    viewer = await operator(identity_engine)
    target = await operator(identity_engine)
    await seed_revisions(identity_engine, target.id, viewer.id, 4)
    async with async_sessionmaker(identity_engine).begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == target.id)
            .values(deleted_at=func.clock_timestamp(), banned_at=func.clock_timestamp())
        )
    result = await reader(identity_engine)(viewer.credential, target.id)
    assert result is not None
    assert result.anchor_version == RETAINED_HEAD
    assert tuple(row.version for row in result.revisions) == (4, 3, 2, 1)
    assert not result.revisions[0].active
    assert result.revisions[0].changed_at < result.revisions[1].changed_at
    assert result.revisions[-1].changed_by_id is None
    assert result.revisions[-1].http_request_id is None
    assert result.revisions[-1].trace_id is None
    async with async_sessionmaker(identity_engine)() as session:
        sources = tuple(
            await session.scalars(
                select(OperatorAccessRevisionRecord)
                .where(OperatorAccessRevisionRecord.account_id == target.id)
                .order_by(OperatorAccessRevisionRecord.version.desc())
            )
        )
        for returned, source in zip(result.revisions, sources, strict=True):
            assert returned.version == source.version
            assert returned.changed_at == source.changed_at
            assert returned.active == source.active
            assert returned.changed_by_id == source.changed_by_id
            assert returned.http_request_id == source.http_request_id
            assert returned.action_id == source.action_id
            assert returned.trace_id == source.trace_id
            assert returned.span_id == source.span_id
        audit = (await session.scalars(select(OperatorAuditRecord))).one()
        event = (await session.scalars(select(ProductEventRecord))).one()
        assert audit.requested_id == target.id
        assert audit.result_ids == [target.id]
        assert event.kind == "operator.inspected"
        assert event.operator_audit_id == audit.id


async def test_version_pagination_ignores_new_head_and_binds_actual_grant_actor_target(
    identity_engine: AsyncEngine,
) -> None:
    viewer = await operator(identity_engine)
    other = await operator(identity_engine)
    target = await operator(identity_engine)
    await seed_revisions(identity_engine, target.id, viewer.id, 52)
    read = reader(identity_engine)
    first = await read(viewer.credential, target.id)
    assert first is not None
    assert first.next_cursor is not None
    assert len(first.revisions) == OPERATOR_ACCESS_HISTORY_PAGE_SIZE
    with pytest.raises(InvalidOperatorCursorError):
        await read(other.credential, target.id, first.next_cursor)
    with pytest.raises(InvalidOperatorCursorError):
        await read(viewer.credential, viewer.id, first.next_cursor)
    async with async_sessionmaker(identity_engine).begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        session.add(
            OperatorAccessRevisionRecord(
                account_id=target.id, version=53, active=True, changed_at=now
            )
        )
        await session.execute(
            update(OperatorAccessRecord)
            .where(OperatorAccessRecord.account_id == target.id)
            .values(current_version=53)
        )
    second = await read(viewer.credential, target.id, first.next_cursor)
    assert second is not None
    assert len(second.revisions) == TAIL_SIZE
    assert tuple(row.version for row in second.revisions) == (2, 1)
    assert second.anchor_version == first.anchor_version
    assert second.next_cursor is None


@pytest.mark.parametrize("denial", ["absent", "revoked", "banned", "deleted"])
async def test_real_current_operator_authority_required(
    identity_engine: AsyncEngine, denial: str
) -> None:
    viewer = (
        await actor(identity_engine)
        if denial == "absent"
        else await operator(identity_engine, active=denial != "revoked")
    )
    target = await operator(identity_engine)
    if denial in {"banned", "deleted"}:
        async with async_sessionmaker(identity_engine).begin() as session:
            await session.execute(
                update(AccountRecord)
                .where(AccountRecord.id == viewer.id)
                .values(
                    banned_at=func.clock_timestamp() if denial == "banned" else None,
                    deleted_at=func.clock_timestamp() if denial == "deleted" else None,
                )
            )
    with pytest.raises(UnauthenticatedError if denial == "deleted" else OperatorAccessDeniedError):
        await reader(identity_engine)(viewer.credential, target.id)
    async with async_sessionmaker(identity_engine)() as session:
        assert tuple(await session.scalars(select(OperatorAuditRecord))) == ()


async def failing_recorder(session: AsyncSession, audit: OperatorAudit) -> None:
    await record_operator_audit(session, audit)
    raise RuntimeError("synthetic canonical failure")


async def cancelled_recorder(session: AsyncSession, audit: OperatorAudit) -> None:
    await record_operator_audit(session, audit)
    raise asyncio.CancelledError


@pytest.mark.parametrize("cancel", [False, True])
async def test_audit_failure_or_cancellation_rolls_back_before_return(
    identity_engine: AsyncEngine, cancel: bool
) -> None:
    viewer = await operator(identity_engine)
    target = await operator(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    read = ReadOperatorAccessHistory(
        SqlOperatorAccessHistoryUnitOfWork(
            sessions, cancelled_recorder if cancel else failing_recorder
        ),
        Sha256SessionHasher(),
        CODEC,
    )
    with pytest.raises(asyncio.CancelledError if cancel else RuntimeError):
        await read(viewer.credential, target.id)
    async with sessions() as session:
        assert tuple(await session.scalars(select(OperatorAuditRecord))) == ()
        assert tuple(await session.scalars(select(ProductEventRecord))) == ()


async def test_existing_unassigned_account_empty_but_missing_audited_not_found(
    identity_engine: AsyncEngine,
) -> None:
    viewer = await operator(identity_engine)
    target = await actor(identity_engine)
    read = reader(identity_engine)
    page = await read(viewer.credential, target.id)
    assert page is not None
    assert page.revisions == ()
    assert page.anchor_version == 0
    assert await read(viewer.credential, uuid4()) is None
    async with async_sessionmaker(identity_engine)() as session:
        assert {row.outcome for row in await session.scalars(select(OperatorAuditRecord))} == {
            "read",
            "not_found",
        }
