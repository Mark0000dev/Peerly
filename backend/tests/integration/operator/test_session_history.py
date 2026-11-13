"""Real retained session metadata, safe projections and transactional inspection."""

from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.engine import Connection, ExecutionContext
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.session_history import ReadOperatorSessionHistory
from studymate.domain.operator.audit import OperatorAudit
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.operator.session_history_cursors import (
    FernetOperatorSessionHistoryCursorCodec,
)
from studymate.infrastructure.operator.session_history_transactions import (
    SqlOperatorSessionHistoryUnitOfWork,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from studymate.presentation.operator.session_history_models import session_history_response
from tests.integration.operator.test_reads import operator
from tests.integration.student_actor import Actor, actor

pytestmark = pytest.mark.integration
DIGEST_BYTES = 32
PAGE_SIZE = 50
REMAINING_COUNT = 2


def reader(engine: AsyncEngine) -> ReadOperatorSessionHistory:
    return ReadOperatorSessionHistory(
        SqlOperatorSessionHistoryUnitOfWork(
            async_sessionmaker(engine, expire_on_commit=False), record_operator_audit
        ),
        Sha256SessionHasher(),
        FernetOperatorSessionHistoryCursorCodec.from_key(b"s" * 32),
    )


async def seeded(
    engine: AsyncEngine, target: Actor, count: int = 1, *, newer: bool = False
) -> tuple[UUID, ...]:
    async with async_sessionmaker(engine).begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        ids = tuple(uuid4() for _ in range(count))
        issued = now if newer else now - timedelta(minutes=2)
        for session_id in ids:
            session.add(
                SessionRecord(
                    id=session_id,
                    account_id=target.id,
                    secret_digest=uuid4().bytes + uuid4().bytes,
                    issued_at=issued,
                    expires_at=issued + timedelta(days=1),
                    revoked_at=None,
                )
            )
    return ids


async def test_exact_retained_dates_after_target_ban_deletion_without_secret_select(
    identity_engine: AsyncEngine,
) -> None:
    viewer, target = await operator(identity_engine), await actor(identity_engine)
    ids = await seeded(identity_engine, target)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == target.id)
            .values(banned_at=func.clock_timestamp(), deleted_at=func.clock_timestamp())
        )
        await session.execute(
            update(SessionRecord)
            .where(SessionRecord.id.in_(ids))
            .values(revoked_at=func.clock_timestamp())
        )
    statements: list[str] = []

    def capture(
        _connection: Connection,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: ExecutionContext,
        _executemany: bool,
    ) -> None:
        if (
            statement.lstrip().upper().startswith("SELECT")
            and "FROM sessions" in statement
            and "ORDER BY sessions.issued_at DESC" in statement
        ):
            statements.append(statement)

    event.listen(identity_engine.sync_engine, "before_cursor_execute", capture)
    try:
        page = await reader(identity_engine)(viewer.credential, target.id)
    finally:
        event.remove(identity_engine.sync_engine, "before_cursor_execute", capture)
    assert page is not None
    row = next(row for row in page.sessions if row.id == ids[0])
    assert row.revoked_at is not None
    assert row.account_id == target.id
    assert len(statements) == 1
    assert "secret_digest" not in statements[0]
    assert "secret_digest" not in session_history_response(page).model_dump_json()
    assert "active" not in session_history_response(page).model_dump_json()
    async with sessions() as session:
        actual = await session.get(SessionRecord, ids[0])
        assert actual is not None
        assert (row.issued_at, row.expires_at, row.revoked_at) == (
            actual.issued_at,
            actual.expires_at,
            actual.revoked_at,
        )
        assert len(actual.secret_digest) == DIGEST_BYTES
        audit = (await session.scalars(select(OperatorAuditRecord))).one()
        canonical = (
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        ).one()
        assert audit.result_ids == [target.id]
        assert canonical.operator_audit_id == audit.id


async def test_issuance_keyset_ties_skip_new_issuance_but_return_fresh_revocation(
    identity_engine: AsyncEngine,
) -> None:
    viewer, target = await operator(identity_engine), await actor(identity_engine)
    ids = await seeded(identity_engine, target, 51)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions() as session:
        original_ids = set(
            await session.scalars(
                select(SessionRecord.id).where(SessionRecord.account_id == target.id)
            )
        )
    assert set(ids) < original_ids
    read = reader(identity_engine)
    first = await read(viewer.credential, target.id)
    assert first is not None
    assert len(first.sessions) == PAGE_SIZE
    assert first.next_cursor is not None
    remaining = original_ids - {row.id for row in first.sessions}
    assert len(remaining) == REMAINING_COUNT
    async with sessions.begin() as session:
        await session.execute(
            update(SessionRecord)
            .where(SessionRecord.id.in_(remaining))
            .values(revoked_at=func.clock_timestamp())
        )
    newer = await seeded(identity_engine, target, newer=True)
    second = await read(viewer.credential, target.id, first.next_cursor)
    assert second is not None
    assert {row.id for row in second.sessions} == remaining
    assert all(row.revoked_at is not None for row in second.sessions)
    assert not (set(newer) & {row.id for row in second.sessions})
    assert second.next_cursor is None
    assert second.as_of == first.as_of


async def test_existing_empty_and_missing_accounts_are_distinct_audited_results(
    identity_engine: AsyncEngine,
) -> None:
    viewer = await operator(identity_engine)
    sessions = async_sessionmaker(identity_engine)
    empty_id = uuid4()
    async with sessions.begin() as session:
        session.add(AccountRecord(id=empty_id, created_at=func.clock_timestamp()))
    read = reader(identity_engine)
    empty = await read(viewer.credential, empty_id)
    assert empty is not None
    assert empty.sessions == ()
    assert empty.next_cursor is None
    assert await read(viewer.credential, uuid4()) is None
    async with sessions() as session:
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
        assert {row.outcome for row in audits} == {"read", "not_found"}


async def fail_audit(session: AsyncSession, audit: OperatorAudit) -> None:
    await record_operator_audit(session, audit)
    raise RuntimeError("synthetic inspection failure")


async def test_canonical_audit_failure_rolls_back_and_returns_no_metadata(
    identity_engine: AsyncEngine,
) -> None:
    viewer, target = await operator(identity_engine), await actor(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    read = ReadOperatorSessionHistory(
        SqlOperatorSessionHistoryUnitOfWork(sessions, fail_audit),
        Sha256SessionHasher(),
        FernetOperatorSessionHistoryCursorCodec.from_key(b"s" * 32),
    )
    with pytest.raises(RuntimeError, match="synthetic inspection failure"):
        await read(viewer.credential, target.id)
    async with sessions() as session:
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


@pytest.mark.parametrize("denial", ["absent", "revoked", "banned", "deleted"])
async def test_actual_role_lifecycle_guards_before_private_history(
    identity_engine: AsyncEngine, denial: str
) -> None:
    viewer = (
        await actor(identity_engine)
        if denial == "absent"
        else await operator(identity_engine, active=denial != "revoked")
    )
    target = await actor(identity_engine)
    sessions = async_sessionmaker(identity_engine)
    if denial in {"banned", "deleted"}:
        async with sessions.begin() as session:
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
    async with sessions() as session:
        assert tuple(await session.scalars(select(OperatorAuditRecord))) == ()
