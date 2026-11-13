"""Real retained rows, keyset/live-state truthfulness and atomic inspection evidence."""

from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.engine import Connection, ExecutionContext
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.email_history import ReadOperatorEmailHistory
from studymate.domain.operator.audit import OperatorAudit
from studymate.domain.operator.email_history import StoredEmailDeliveryStatus
from studymate.infrastructure.operator.email_history_cursors import (
    FernetOperatorEmailHistoryCursorCodec,
)
from studymate.infrastructure.operator.email_history_transactions import (
    SqlOperatorEmailHistoryUnitOfWork,
)
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.persistence.email_models import (
    EmailChallengeRecord,
    EmailDeliveryRecord,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from studymate.presentation.operator.email_history_models import email_history_response
from tests.integration.operator.membership_verification_test import prepared
from tests.integration.operator.test_reads import operator
from tests.integration.student_actor import Actor, actor

pytestmark = pytest.mark.integration
PAGE_SIZE = 50
REMAINING_COUNT = 2
CHALLENGE_ATTEMPTS = 2


def reader(engine: AsyncEngine) -> ReadOperatorEmailHistory:
    return ReadOperatorEmailHistory(
        SqlOperatorEmailHistoryUnitOfWork(
            async_sessionmaker(engine, expire_on_commit=False), record_operator_audit
        ),
        Sha256SessionHasher(),
        FernetOperatorEmailHistoryCursorCodec.from_key(b"e" * 32),
    )


async def seeded(
    engine: AsyncEngine, target: Actor, count: int = 1, *, newer: bool = False
) -> tuple[UUID, ...]:
    async with async_sessionmaker(engine).begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        session_id = await session.scalar(
            select(SessionRecord.id).where(SessionRecord.account_id == target.id)
        )
        assert session_id is not None
        ids = tuple(uuid4() for _ in range(count))
        for index, challenge_id in enumerate(ids):
            # Equal timestamps exercise UUID tie-breaking, not accidental insertion order.
            created = now if newer else now - timedelta(minutes=1)
            session.add(
                EmailChallengeRecord(
                    id=challenge_id,
                    account_id=target.id,
                    session_id=session_id,
                    email="retained-actual@mail.apu.edu.my",
                    code_digest=b"c" * 32,
                    source_digest=b"s" * 32,
                    created_at=created,
                    resend_at=created + timedelta(minutes=2),
                    expires_at=created + timedelta(minutes=10),
                    attempts=2,
                    consumed_at=None,
                    superseded_at=now if index < count - 1 else None,
                )
            )
        await session.flush()
        session.add(
            EmailDeliveryRecord(
                id=uuid4(),
                challenge_id=ids[-1],
                status="queued",
                sealed_envelope=b"private-synthetic-envelope",
                created_at=now,
                due_at=now,
                attempts=1,
                lease_generation=0,
                lease_until=None,
                delivered_at=None,
                last_error="provider_unavailable",
                origin_request_id=uuid4(),
                origin_action_id=uuid4(),
                origin_trace_id="a" * 32,
                origin_span_id="b" * 16,
            )
        )
    return ids


async def test_exact_safe_metadata_retained_after_target_deletion_and_audited(
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
            and "email_challenges" in statement
            and "email_outbox" in statement
        ):
            statements.append(statement)

    event.listen(identity_engine.sync_engine, "before_cursor_execute", capture)
    try:
        page = await reader(identity_engine)(viewer.credential, target.id)
    finally:
        event.remove(identity_engine.sync_engine, "before_cursor_execute", capture)
    assert page is not None
    row = page.challenges[0]
    assert row.id == ids[0]
    assert row.account_id == target.id
    assert row.attempts == CHALLENGE_ATTEMPTS
    assert row.delivery is not None
    assert row.delivery.status == StoredEmailDeliveryStatus.QUEUED
    assert row.delivery.attempts == 1
    assert row.delivery.last_error == "provider_unavailable"
    assert row.delivery.origin_trace_id == "a" * 32
    assert row.manual_verification is None
    assert row.consumed_at is None
    assert len(statements) == 1
    for forbidden in (
        "code_digest",
        "source_digest",
        "sealed_envelope",
        "lease_until",
        "lease_generation",
    ):
        assert forbidden not in statements[0]
        assert forbidden not in email_history_response(page).model_dump_json()
    async with sessions() as session:
        challenge = await session.get(EmailChallengeRecord, ids[0])
        delivery = (await session.scalars(select(EmailDeliveryRecord))).one()
        assert challenge is not None
        assert challenge.code_digest == b"c" * 32
        assert challenge.consumed_at is None
        assert delivery.sealed_envelope == b"private-synthetic-envelope"
        assert delivery.status == "queued"
        audit = (await session.scalars(select(OperatorAuditRecord))).one()
        canonical = (
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        ).one()
        assert audit.result_ids == [target.id]
        assert canonical.operator_audit_id == audit.id
        assert "retained-actual" not in repr(audit)


async def test_keyset_equal_time_no_duplicates_and_fresh_delivery_state(
    identity_engine: AsyncEngine,
) -> None:
    viewer, target = await operator(identity_engine), await actor(identity_engine)
    ids = await seeded(identity_engine, target, 52)
    read = reader(identity_engine)
    first = await read(viewer.credential, target.id)
    assert first is not None
    assert len(first.challenges) == PAGE_SIZE
    assert first.next_cursor is not None
    remaining = set(ids) - {row.id for row in first.challenges}
    assert len(remaining) == REMAINING_COUNT
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        await session.execute(
            update(EmailChallengeRecord)
            .where(EmailChallengeRecord.id.in_(remaining))
            .values(consumed_at=func.clock_timestamp(), superseded_at=None)
        )
    # New rows with creation after as_of are excluded; previous mutable rows are current.
    async with sessions.begin() as session:
        await session.execute(
            update(EmailChallengeRecord)
            .where(
                EmailChallengeRecord.account_id == target.id,
                EmailChallengeRecord.consumed_at.is_(None),
                EmailChallengeRecord.superseded_at.is_(None),
            )
            .values(superseded_at=func.clock_timestamp())
        )
    later = await seeded(identity_engine, target, newer=True)
    second = await read(viewer.credential, target.id, first.next_cursor)
    assert second is not None
    assert {row.id for row in second.challenges} == remaining
    assert all(row.consumed_at is not None for row in second.challenges)
    assert not ({row.id for row in second.challenges} & set(later))
    assert second.next_cursor is None
    assert second.as_of == first.as_of


async def test_manual_source_is_actual_fk_bound_record_not_inferred_from_delivery(
    identity_engine: AsyncEngine,
) -> None:
    case = await prepared(identity_engine)
    actual = await case.verify()(case.command)
    page = await reader(identity_engine)(case.operator.credential, case.target.id)
    assert page is not None
    assert len(page.challenges) == 1
    row = page.challenges[0]
    assert row.id == actual.challenge_id
    assert row.consumed_at is None
    assert row.superseded_at == actual.verified_at
    assert row.manual_verification is not None
    assert row.manual_verification.id == actual.id
    assert row.manual_verification.event_id == actual.event_id
    assert row.manual_verification.operator_id == actual.operator.account_id
    assert row.manual_verification.verified_at == actual.verified_at
    assert row.delivery is not None
    assert row.delivery.status == StoredEmailDeliveryStatus.CANCELLED


async def fail_audit(session: AsyncSession, audit: OperatorAudit) -> None:
    await record_operator_audit(session, audit)
    raise RuntimeError("synthetic inspection failure")


async def test_audit_failure_rolls_back_canonical_write_and_returns_no_history(
    identity_engine: AsyncEngine,
) -> None:
    viewer, target = await operator(identity_engine), await actor(identity_engine)
    await seeded(identity_engine, target)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    read = ReadOperatorEmailHistory(
        SqlOperatorEmailHistoryUnitOfWork(sessions, fail_audit),
        Sha256SessionHasher(),
        FernetOperatorEmailHistoryCursorCodec.from_key(b"e" * 32),
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
async def test_actual_role_lifecycle_guards_before_any_private_read(
    identity_engine: AsyncEngine, denial: str
) -> None:
    viewer = (
        await actor(identity_engine)
        if denial == "absent"
        else await operator(identity_engine, active=denial != "revoked")
    )
    target = await actor(identity_engine)
    await seeded(identity_engine, target)
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
