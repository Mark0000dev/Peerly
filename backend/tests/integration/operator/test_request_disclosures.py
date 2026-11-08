"""Actual retained disclosure/ACK rows under audited privileged read transactions."""

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import require_operator
from studymate.application.operator.cursors import InvalidOperatorCursorError
from studymate.application.operator.disclosure_ports import OperatorDisclosureFilters
from studymate.application.operator.request_disclosures import ReadOperatorRequestDisclosures
from studymate.domain.operator.audit import OperatorAudit
from studymate.domain.operator.request_disclosures import OPERATOR_DISCLOSURE_PAGE_SIZE
from studymate.infrastructure.operator.disclosure_cursors import FernetOperatorDisclosureCursorCodec
from studymate.infrastructure.operator.disclosure_transactions import (
    SqlOperatorDisclosureTransaction,
    SqlOperatorDisclosureUnitOfWork,
)
from studymate.infrastructure.operator.models import OperatorAccessRecord, OperatorAuditRecord
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from studymate.infrastructure.requests.models import (
    ConnectionRequestRecord,
    RequestCommandIntentRecord,
    RequestRevisionRecord,
    RequestSendDayRecord,
)
from studymate.infrastructure.requests.view_models import (
    RequestDisclosureRecord,
    RequestViewAcknowledgementRecord,
)
from tests.integration.operator.test_connection_requests import Requests, prepared, seed_history
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration
CODEC = FernetOperatorDisclosureCursorCodec.from_key(b"d" * 32)


def uow(api: Requests) -> SqlOperatorDisclosureUnitOfWork:
    return SqlOperatorDisclosureUnitOfWork(api.api.sessions, record_operator_audit)


def reader(api: Requests) -> ReadOperatorRequestDisclosures:
    return ReadOperatorRequestDisclosures(uow(api), HASHER, FINGERPRINTER, CODEC)


async def seed_disclosures(
    session: AsyncSession,
    api: Requests,
    count: int,
    *,
    acknowledgements: bool = True,
) -> tuple[UUID, ...]:
    ids = tuple(UUID(int=4000 + index) for index in range(count))
    for index, identifier in enumerate(ids):
        viewer = api.sender.id if index == 0 else api.recipient.id
        session.add(
            RequestDisclosureRecord(
                id=identifier,
                viewer_id=viewer,
                request_id=api.request.id,
                stored_version=1,
                sender_id=api.sender.id,
                recipient_id=api.recipient.id,
                created_at=api.request.sent_at + timedelta(days=1),
                http_request_id=None,
                action_id=uuid4(),
                trace_id="legacy-source-trace",
                span_id=None,
            )
        )
    await session.flush()
    if acknowledgements:
        for identifier in dict.fromkeys((ids[0], ids[-1])):
            row = await session.get(RequestDisclosureRecord, identifier)
            assert row is not None
            session.add(
                RequestViewAcknowledgementRecord(
                    id=uuid4(),
                    viewer_id=row.viewer_id,
                    request_id=row.request_id,
                    stored_version=row.stored_version,
                    disclosure_id=row.id,
                    acknowledged_at=api.request.sent_at,
                    http_request_id=None,
                    action_id=None,
                    trace_id=None,
                    span_id="legacy-span",
                )
            )
        await session.flush()
    return ids


async def source_counts(session: AsyncSession) -> tuple[int, ...]:
    values = []
    for model in (
        RequestDisclosureRecord,
        RequestViewAcknowledgementRecord,
        ConnectionRequestRecord,
        RequestRevisionRecord,
        RequestCommandIntentRecord,
        RequestSendDayRecord,
    ):
        value = await session.scalar(select(func.count()).select_from(model))
        assert value is not None
        values.append(value)
    return tuple(values)


async def test_all_repeated_unacked_rows_page_exact_acks_and_no_source_writes(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    async with api.uow.sessions.begin() as session:
        ids = await seed_disclosures(session, api, OPERATOR_DISCLOSURE_PAGE_SIZE + 3)
        # More stored history than current pointer; every technical disclosure stays version1.
        await seed_history(session, api, (1, 9))
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == api.sender.id)
            .values(
                banned_at=api.request.sent_at,
                deleted_at=api.request.sent_at,
            )
        )
        before = await source_counts(session)
    first = await reader(api)(
        api.owner.credential, api.sender.id, api.request.id, OperatorDisclosureFilters()
    )
    assert first is not None
    assert first.next_cursor is not None
    assert len(first.disclosures) == OPERATOR_DISCLOSURE_PAGE_SIZE
    assert first.anchor_created_at is not None
    assert first.anchor_created_at > first.observed_at
    assert first.anchor_disclosure_id == ids[-1]
    assert {row.stored_version for row in first.disclosures} == {1}
    assert first.request.current_version == 1
    assert tuple(row.disclosure.id for row in first.acknowledgements) == ids[-1:]
    assert first.disclosures[0].origin.trace_id == "legacy-source-trace"
    assert first.acknowledgements[0].origin.span_id == "legacy-span"
    async with api.uow.sessions.begin() as session:
        session.add(
            RequestDisclosureRecord(
                id=uuid4(),
                viewer_id=api.sender.id,
                request_id=api.request.id,
                stored_version=1,
                sender_id=api.sender.id,
                recipient_id=api.recipient.id,
                created_at=api.request.sent_at + timedelta(days=2),
                http_request_id=None,
                action_id=None,
                trace_id=None,
                span_id=None,
            )
        )
    second = await reader(api)(
        api.owner.credential,
        api.sender.id,
        api.request.id,
        OperatorDisclosureFilters(),
        first.next_cursor,
    )
    assert second is not None
    assert tuple(row.id for row in second.disclosures) == tuple(reversed(ids[:3]))
    assert tuple(row.disclosure.id for row in second.acknowledgements) == ids[:1]
    assert not second.next_cursor
    recipient = await reader(api)(
        api.owner.credential, api.recipient.id, api.request.id, OperatorDisclosureFilters()
    )
    assert recipient is not None
    async with api.uow.sessions() as session:
        after = await source_counts(session)
        assert after[0] == before[0] + 1
        assert after[1:] == before[1:]
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
        assert len(audits) == len((first, second, recipient))
        assert all(row.action == "read_account" and row.outcome == "read" for row in audits)
        assert all(row.operator_id == api.owner.id for row in audits)
        events = tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        )
        assert len(events) == len(audits)


async def test_all_bounded_fact_filters_and_cursor_scopes(identity_engine: AsyncEngine) -> None:
    api = await prepared(identity_engine)
    async with api.uow.sessions.begin() as session:
        ids = await seed_disclosures(session, api, OPERATOR_DISCLOSURE_PAGE_SIZE + 1)
        ack_id = await session.scalar(
            select(RequestViewAcknowledgementRecord.id).where(
                RequestViewAcknowledgementRecord.disclosure_id == ids[0]
            )
        )
        assert ack_id is not None
    for filters in (
        OperatorDisclosureFilters(viewer_id=api.sender.id),
        OperatorDisclosureFilters(disclosure_id=ids[0]),
        OperatorDisclosureFilters(acknowledgement_id=ack_id),
        OperatorDisclosureFilters(
            disclosure_id=ids[0],
            stored_version=1,
            created_from=api.request.sent_at + timedelta(days=1),
            created_before=api.request.sent_at + timedelta(days=2),
        ),
    ):
        page = await reader(api)(api.owner.credential, api.sender.id, api.request.id, filters)
        assert page is not None
        assert tuple(row.id for row in page.disclosures) == ids[:1]
    for filters in (
        OperatorDisclosureFilters(stored_version=2),
        OperatorDisclosureFilters(viewer_id=uuid4()),
        OperatorDisclosureFilters(disclosure_id=uuid4()),
        OperatorDisclosureFilters(acknowledgement_id=uuid4()),
        OperatorDisclosureFilters(created_before=api.request.sent_at + timedelta(days=1)),
        OperatorDisclosureFilters(created_from=api.request.sent_at + timedelta(days=2)),
    ):
        page = await reader(api)(api.owner.credential, api.sender.id, api.request.id, filters)
        assert page is not None
        assert not page.disclosures
        assert not page.acknowledgements
    first = await reader(api)(
        api.owner.credential, api.sender.id, api.request.id, OperatorDisclosureFilters()
    )
    assert first is not None
    assert first.next_cursor is not None
    with pytest.raises(InvalidOperatorCursorError):
        await reader(api)(
            api.owner.credential,
            api.recipient.id,
            api.request.id,
            OperatorDisclosureFilters(),
            first.next_cursor,
        )
    with pytest.raises(InvalidOperatorCursorError):
        await reader(api)(
            api.owner.credential,
            api.sender.id,
            api.request.id,
            OperatorDisclosureFilters(stored_version=1),
            first.next_cursor,
        )


async def test_neutral_missing_foreign_child_and_missing_parent_audit(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    outsider = await actor(identity_engine)
    missing = uuid4()
    for account, request in (
        (api.sender.id, missing),
        (outsider.id, api.request.id),
        (missing, api.request.id),
    ):
        assert (
            await reader(api)(api.owner.credential, account, request, OperatorDisclosureFilters())
            is None
        )
    empty = await reader(api)(
        api.owner.credential, api.sender.id, api.request.id, OperatorDisclosureFilters()
    )
    assert empty is not None
    assert not empty.disclosures
    async with api.uow.sessions() as session:
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
        assert all(
            row.result_ids == [row.requested_id] and row.outcome == "read"
            for row in audits
            if row.requested_id != missing
        )
        assert all(
            row.result_ids == [] and row.outcome == "not_found"
            for row in audits
            if row.requested_id == missing
        )


async def test_sql_selects_no_body_intent_or_private_source_and_no_unchecked_access(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    async with api.uow.sessions.begin() as session:
        await seed_disclosures(session, api, 1)
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
        assert (
            await reader(api)(
                api.owner.credential, api.sender.id, api.request.id, OperatorDisclosureFilters()
            )
            is not None
        )
    finally:
        event.remove(identity_engine.sync_engine, "before_cursor_execute", capture)
    sources = [
        sql
        for sql in statements
        if sql.startswith("select ")
        and (
            "from connection_requests" in sql
            or "from request_disclosures" in sql
            or "from request_view_acknowledgements" in sql
        )
    ]
    assert sources
    for source in sources:
        for forbidden in (
            "request_text",
            "source_json",
            "connection_requests.note",
            "request_command_intents",
            "fingerprint",
        ):
            assert forbidden not in source
    async with api.uow.sessions() as session:
        transaction = SqlOperatorDisclosureTransaction(session, record_operator_audit)
        with pytest.raises(RuntimeError, match="operator"):
            await transaction.disclosure_account(api.sender.id)
    async with uow(api).transaction() as transaction:
        await require_operator(transaction, api.owner.credential, HASHER)
        assert not await transaction.disclosure_page_acknowledgements(
            api.sender.id, api.request.id, ()
        )
        with pytest.raises(ValueError, match="visible page"):
            await transaction.disclosure_page_acknowledgements(
                api.sender.id,
                api.request.id,
                tuple(uuid4() for _ in range(OPERATOR_DISCLOSURE_PAGE_SIZE + 1)),
            )


async def test_canonical_failure_rolls_back_both_audit_and_event(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)

    async def fail(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        raise StorageUnavailableError

    operation = replace(reader(api), unit_of_work=replace(uow(api), recorder=fail))
    with pytest.raises(StorageUnavailableError):
        await operation(
            api.owner.credential, api.sender.id, api.request.id, OperatorDisclosureFilters()
        )
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
        assert not tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        )


async def test_final_committed_session_deadline_prevents_return_after_audit(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    async with api.uow.sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        deadline = now + timedelta(seconds=2)
        await session.execute(
            update(SessionRecord)
            .where(SessionRecord.account_id == api.owner.id)
            .values(expires_at=deadline)
        )
    entered = False

    async def expire(session: AsyncSession, audit: OperatorAudit) -> None:
        nonlocal entered
        await record_operator_audit(session, audit)
        entered = True
        current = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(current, datetime)
        await session.execute(
            select(func.pg_sleep(max(0, (deadline - current).total_seconds()) + 0.05))
        )

    with pytest.raises(UnauthenticatedError):
        await replace(reader(api), unit_of_work=replace(uow(api), recorder=expire))(
            api.owner.credential, api.sender.id, api.request.id, OperatorDisclosureFilters()
        )
    assert entered
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))


async def test_cancellation_rolls_back_and_releases_operator_auth_locks(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def paused(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        entered.set()
        await release.wait()

    operation = replace(reader(api), unit_of_work=replace(uow(api), recorder=paused))
    task = asyncio.create_task(
        operation(api.owner.credential, api.sender.id, api.request.id, OperatorDisclosureFilters())
    )
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release.set()
        if not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
    assert (
        await asyncio.wait_for(
            reader(api)(
                api.owner.credential, api.sender.id, api.request.id, OperatorDisclosureFilters()
            ),
            timeout=5,
        )
        is not None
    )


async def test_real_deferred_commit_failure_returns_no_page(identity_engine: AsyncEngine) -> None:
    api = await prepared(identity_engine)
    staged = False

    async def invalid_commit(session: AsyncSession, audit: OperatorAudit) -> None:
        nonlocal staged
        await record_operator_audit(session, audit)
        await session.execute(
            update(OperatorAccessRecord)
            .where(OperatorAccessRecord.account_id == api.owner.id)
            .values(current_version=2)
        )
        await session.flush()
        staged = True

    with pytest.raises(IntegrityError, match="fk_operator_access_current_revision"):
        await replace(reader(api), unit_of_work=replace(uow(api), recorder=invalid_commit))(
            api.owner.credential, api.sender.id, api.request.id, OperatorDisclosureFilters()
        )
    assert staged
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
        assert not tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        )
        assert (
            await session.scalar(
                select(OperatorAccessRecord.current_version).where(
                    OperatorAccessRecord.account_id == api.owner.id
                )
            )
            == 1
        )
    assert (
        await reader(api)(
            api.owner.credential, api.sender.id, api.request.id, OperatorDisclosureFilters()
        )
        is not None
    )
