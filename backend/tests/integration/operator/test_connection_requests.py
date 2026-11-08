"""Actual retained Request/Preview/Revision/ACK sources, without Requests read/write workflows."""

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.connection_requests import (
    ReadOperatorRequestHistory,
    ReadOperatorRequests,
)
from studymate.application.operator.request_ports import (
    OperatorRequestDirection,
    OperatorRequestFilters,
)
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.operator.audit import OperatorAudit
from studymate.domain.operator.connection_requests import OPERATOR_REQUEST_PAGE_SIZE
from studymate.domain.requests.states import ConnectionRequest, RequestState
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.operator.request_cursors import FernetOperatorRequestCursorCodec
from studymate.infrastructure.operator.request_transactions import (
    SqlOperatorRequestTransaction,
    SqlOperatorRequestUnitOfWork,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from studymate.infrastructure.requests.models import (
    ConnectionRequestRecord,
    RequestCommandIntentRecord,
    RequestPreviewRecord,
    RequestRevisionRecord,
    RequestSendDayRecord,
)
from studymate.infrastructure.requests.view_models import (
    RequestDisclosureRecord,
    RequestViewAcknowledgementRecord,
)
from tests.integration.operator.test_reads import operator
from tests.integration.profile_lifecycle_fixture import command as hidden_command
from tests.integration.profile_lifecycle_fixture import services as visibility_services
from tests.integration.requests.fixture import FINGERPRINTER, HASHER, Services, action, sent
from tests.integration.requests.fixture import prepared as request_prepared
from tests.integration.student_actor import Actor, actor

pytestmark = pytest.mark.integration
CODEC = FernetOperatorRequestCursorCodec.from_key(b"r" * 32)
RAW_TEXT = "  Private original reviewed text  "
RAW_NOTE = "  Private old note  "
RAW_JSON = ' { "unknown_legacy_schema": "Private retained academic material" }\n'


@dataclass(frozen=True, slots=True)
class Requests:
    owner: Actor
    sender: Actor
    recipient: Actor
    api: Services
    request: ConnectionRequest
    uow: SqlOperatorRequestUnitOfWork

    def roots(self) -> ReadOperatorRequests:
        return ReadOperatorRequests(self.uow, HASHER, FINGERPRINTER, CODEC)

    def history(self) -> ReadOperatorRequestHistory:
        return ReadOperatorRequestHistory(self.uow, HASHER, CODEC)


async def prepared(engine: AsyncEngine) -> Requests:
    first, second, api = await request_prepared(engine)
    request = await sent(api, first, second)
    owner = await operator(engine)
    return Requests(
        owner,
        first,
        second,
        api,
        request,
        SqlOperatorRequestUnitOfWork(api.sessions, record_operator_audit),
    )


async def seed_history(
    session: AsyncSession, api: Requests, versions: tuple[int, ...], *, acks: bool = False
) -> None:
    for version in versions:
        if version != 1:
            session.add(
                RequestRevisionRecord(
                    request_id=api.request.id,
                    version=version,
                    state="withdrawn",
                    changed_at=api.request.sent_at - timedelta(seconds=version),
                    decline_until=None,
                    conversation_id=None,
                )
            )
    await session.flush()
    if not acks:
        return
    for version in versions:
        for viewer in (api.sender.id, api.recipient.id):
            disclosure = RequestDisclosureRecord(
                id=uuid4(),
                viewer_id=viewer,
                request_id=api.request.id,
                stored_version=version,
                sender_id=api.sender.id,
                recipient_id=api.recipient.id,
                created_at=api.request.sent_at,
                http_request_id=None,
                action_id=uuid4(),
                trace_id="legacy-source",
                span_id=None,
            )
            session.add(disclosure)
            await session.flush()
            session.add(
                RequestViewAcknowledgementRecord(
                    id=uuid4(),
                    viewer_id=viewer,
                    request_id=api.request.id,
                    stored_version=version,
                    disclosure_id=disclosure.id,
                    acknowledged_at=api.request.sent_at,
                    http_request_id=None,
                    action_id=uuid4(),
                    trace_id=None,
                    span_id="legacy-span",
                )
            )
    await session.flush()


async def seed_root(
    session: AsyncSession, api: Requests, at: datetime, sequence: int, *, incoming: bool = False
) -> UUID:
    original = await session.get(ConnectionRequestRecord, api.request.id)
    assert original is not None
    preview_id = original.preview_id
    if incoming:
        preview = await session.get(RequestPreviewRecord, preview_id)
        assert preview is not None
        other = RequestPreviewRecord(
            id=uuid4(),
            sender_id=api.recipient.id,
            recipient_id=api.sender.id,
            mode="offer_help",
            subject_id=preview.subject_id,
            created_at=at,
            source_json=RAW_JSON,
            sender_goal_id=None,
            sender_goal_version=None,
            recipient_goal_id=preview.sender_goal_id,
            recipient_goal_version=preview.sender_goal_version,
            sender_help_version=preview.recipient_help_version,
            recipient_help_version=None,
        )
        session.add(other)
        await session.flush()
        preview_id = other.id
    request_id = uuid4()
    session.add(
        ConnectionRequestRecord(
            id=request_id,
            relationship_id=original.relationship_id,
            low_id=original.low_id,
            high_id=original.high_id,
            sender_id=api.recipient.id if incoming else api.sender.id,
            recipient_id=api.sender.id if incoming else api.recipient.id,
            preview_id=preview_id,
            request_text=RAW_TEXT,
            note=RAW_NOTE,
            sent_at=at,
            expires_at=at + timedelta(days=7),
            current_version=2,
            state="withdrawn",
            decision_sequence=sequence,
            request_id=None,
            action_id=None,
            trace_id=None,
            span_id=None,
        )
    )
    await session.flush()
    session.add_all(
        (
            RequestRevisionRecord(
                request_id=request_id,
                version=1,
                state="pending",
                changed_at=at,
                decline_until=None,
                conversation_id=None,
            ),
            RequestRevisionRecord(
                request_id=request_id,
                version=2,
                state="withdrawn",
                changed_at=at,
                decline_until=None,
                conversation_id=None,
            ),
        )
    )
    await session.flush()
    return request_id


async def test_both_participant_scopes_keep_raw_legacy_body_after_hide_ban_and_deletion(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    visibility, _ = visibility_services(identity_engine)
    await visibility(hidden_command(api.sender))
    async with api.uow.sessions.begin() as session:
        await session.execute(
            update(RequestPreviewRecord)
            .where(RequestPreviewRecord.id == api.request.preview_id)
            .values(source_json=RAW_JSON)
        )
        await session.execute(
            update(ConnectionRequestRecord)
            .where(ConnectionRequestRecord.id == api.request.id)
            .values(
                request_text=RAW_TEXT,
                note=RAW_NOTE,
                request_id=None,
                action_id=uuid4(),
                trace_id="legacy-not-hex",
                span_id=None,
            )
        )
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == api.sender.id)
            .values(banned_at=func.clock_timestamp(), deleted_at=func.clock_timestamp())
        )
    for account in (api.sender.id, api.recipient.id):
        page = await api.history()(api.owner.credential, account, api.request.id)
        assert page is not None
        assert page.snapshot.request_text == RAW_TEXT
        assert page.snapshot.note == RAW_NOTE
        assert page.snapshot.preview.source_json_raw == RAW_JSON
        assert page.snapshot.root.origin.trace_id == "legacy-not-hex"
        assert page.snapshot.root.origin.http_request_id is None
        assert RAW_TEXT not in repr(page)
    async with api.uow.sessions() as session:
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
        assert {row.requested_id for row in audits} == {api.sender.id, api.recipient.id}
        assert all(
            row.action == "read_account" and row.result_ids == [row.requested_id] for row in audits
        )


async def test_raw_pending_decline_deadline_passage_does_not_settle_or_ack(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    declined = await api.api.decline(action(api.recipient, api.sender, api.request))
    async with api.uow.sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        at = now - timedelta(minutes=1)
        await session.execute(
            update(RequestRevisionRecord)
            .where(
                RequestRevisionRecord.request_id == declined.id,
                RequestRevisionRecord.version == declined.version,
            )
            .values(changed_at=at, decline_until=at + timedelta(seconds=10))
        )
        before_events = await session.scalar(select(func.count()).select_from(ProductEventRecord))
        assert before_events is not None
    page = await api.history()(api.owner.credential, api.sender.id, declined.id)
    assert page is not None
    assert page.snapshot.root.state == RequestState.PENDING_DECLINE
    assert page.revisions[0].decline_until is not None
    assert page.revisions[0].decline_until < page.observed_at
    async with api.uow.sessions() as session:
        assert (
            await session.scalar(
                select(ConnectionRequestRecord.state).where(
                    ConnectionRequestRecord.id == declined.id
                )
            )
            == "pending_decline"
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(RequestRevisionRecord)
                .where(RequestRevisionRecord.request_id == declined.id)
            )
            == declined.version
        )
        assert (
            await session.scalar(select(func.count()).select_from(ProductEventRecord))
            == before_events + 1
        )
        assert not tuple(await session.scalars(select(RequestViewAcknowledgementRecord)))
        assert not tuple(await session.scalars(select(RequestDisclosureRecord)))


async def test_current_pointer_does_not_hide_versions_gaps_or_page_linked_acks(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    versions = tuple(range(1, OPERATOR_REQUEST_PAGE_SIZE + 4))
    async with api.uow.sessions.begin() as session:
        await seed_history(session, api, versions, acks=True)
    first = await api.history()(api.owner.credential, api.sender.id, api.request.id)
    assert first is not None
    assert first.next_cursor is not None
    assert first.snapshot.root.current_version == 1
    assert first.anchor_version == max(versions)
    assert len(first.revisions) == OPERATOR_REQUEST_PAGE_SIZE
    assert len(first.acknowledgements) == OPERATOR_REQUEST_PAGE_SIZE * 2
    visible = {row.version for row in first.revisions}
    assert all(
        row.stored_version in visible and row.disclosure.id is not None
        for row in first.acknowledgements
    )
    assert first.acknowledgements[0].disclosure.origin.trace_id == "legacy-source"
    assert first.acknowledgements[0].origin.span_id == "legacy-span"
    second = await api.history()(api.owner.credential, api.recipient.id, api.request.id)
    assert second is not None
    last = await api.history()(
        api.owner.credential, api.sender.id, api.request.id, first.next_cursor
    )
    assert last is not None
    assert tuple(row.version for row in last.revisions) == (3, 2, 1)
    assert len(last.acknowledgements) == len((1, 2, 3)) * 2
    assert all(row.stored_version in {1, 2, 3} for row in last.acknowledgements)


async def test_gapped_raw_history_and_actual_accepted_conversation_reference(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    accepted = await api.api.accept(action(api.recipient, api.sender, api.request))
    conversation_id = accepted.conversation.id
    async with api.uow.sessions.begin() as session:
        session.add(
            RequestRevisionRecord(
                request_id=api.request.id,
                version=99,
                state="expired",
                changed_at=api.request.sent_at - timedelta(days=1),
                decline_until=None,
                conversation_id=None,
            )
        )
    page = await api.history()(api.owner.credential, api.sender.id, api.request.id)
    assert page is not None
    assert tuple(row.version for row in page.revisions) == (99, 2, 1)
    assert page.revisions[1].state == RequestState.ACCEPTED
    assert page.revisions[1].conversation_id == conversation_id
    assert page.snapshot.root.current_version == accepted.request.version


async def test_metadata_keyset_direction_peer_mode_state_and_future_anchor(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    async with api.uow.sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        sequence = await session.scalar(select(func.max(ConnectionRequestRecord.decision_sequence)))
        assert sequence is not None
        for index in range(OPERATOR_REQUEST_PAGE_SIZE + 2):
            await seed_root(session, api, now + timedelta(minutes=index), sequence + index + 1)
        incoming = await seed_root(session, api, now - timedelta(minutes=1), 1, incoming=True)
    filters = OperatorRequestFilters(
        peer_id=api.recipient.id,
        direction=OperatorRequestDirection.SENT,
        mode=DiscoveryMode.FIND_HELP,
        state=RequestState.WITHDRAWN,
        sent_from=now,
    )
    first = await api.roots()(api.owner.credential, api.sender.id, filters)
    assert first is not None
    assert first.next_cursor is not None
    assert len(first.requests) == OPERATOR_REQUEST_PAGE_SIZE
    assert first.anchor_sent_at is not None
    assert first.anchor_sent_at > first.observed_at
    last = await api.roots()(api.owner.credential, api.sender.id, filters, first.next_cursor)
    assert last is not None
    assert len(last.requests) == len((1, 2))
    received = await api.roots()(
        api.owner.credential,
        api.sender.id,
        OperatorRequestFilters(
            direction=OperatorRequestDirection.RECEIVED,
            mode=DiscoveryMode.OFFER_HELP,
            sent_before=now,
        ),
    )
    assert received is not None
    assert tuple(row.id for row in received.requests) == (incoming,)


async def test_metadata_sql_never_selects_bodies_intent_keys_or_fingerprints(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
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
        page = await api.roots()(api.owner.credential, api.sender.id, OperatorRequestFilters())
        assert page is not None
    finally:
        event.remove(identity_engine.sync_engine, "before_cursor_execute", capture)
    sources = [
        sql for sql in statements if sql.startswith("select ") and "from connection_requests" in sql
    ]
    assert len(sources) == 1
    for private in (
        "request_text",
        "connection_requests.note",
        "source_json",
        "request_command_intents",
        "fingerprint",
    ):
        assert private not in sources[0]


async def test_unacked_disclosures_are_not_returned_as_acks_or_mutated(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    async with api.uow.sessions.begin() as session:
        for _ in range(10):
            session.add(
                RequestDisclosureRecord(
                    id=uuid4(),
                    viewer_id=api.sender.id,
                    request_id=api.request.id,
                    stored_version=1,
                    sender_id=api.sender.id,
                    recipient_id=api.recipient.id,
                    created_at=api.request.sent_at,
                    http_request_id=None,
                    action_id=None,
                    trace_id=None,
                    span_id=None,
                )
            )
        await session.flush()
        before_views = await session.scalar(
            select(func.count()).select_from(RequestDisclosureRecord)
        )
        before_intents = await session.scalar(
            select(func.count()).select_from(RequestCommandIntentRecord)
        )
        before_sends = await session.scalar(select(func.sum(RequestSendDayRecord.successful_count)))
    page = await api.history()(api.owner.credential, api.sender.id, api.request.id)
    assert page is not None
    assert page.acknowledgements == ()
    async with api.uow.sessions() as session:
        assert (
            await session.scalar(select(func.count()).select_from(RequestDisclosureRecord))
            == before_views
        )
        assert (
            await session.scalar(select(func.count()).select_from(RequestCommandIntentRecord))
            == before_intents
        )
        assert (
            await session.scalar(select(func.sum(RequestSendDayRecord.successful_count)))
            == before_sends
        )
        assert not tuple(await session.scalars(select(RequestViewAcknowledgementRecord)))


async def test_missing_parent_foreign_child_and_empty_account_are_neutral_and_audited(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    third = await actor(identity_engine)
    assert await api.history()(api.owner.credential, third.id, api.request.id) is None
    assert await api.history()(api.owner.credential, api.sender.id, uuid4()) is None
    missing = uuid4()
    assert await api.history()(api.owner.credential, missing, api.request.id) is None
    empty = await api.roots()(api.owner.credential, third.id, OperatorRequestFilters())
    assert empty is not None
    assert not empty.requests
    assert await api.roots()(api.owner.credential, missing, OperatorRequestFilters()) is None
    async with api.uow.sessions() as session:
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
        assert all(
            row.outcome == "not_found" and row.result_ids == []
            for row in audits
            if row.requested_id == missing
        )
        assert all(
            row.outcome == "read" and row.result_ids == [row.requested_id]
            for row in audits
            if row.requested_id != missing
        )


@pytest.mark.parametrize("read_history", [True, False])
async def test_actual_canonical_failure_rolls_back_inspection_before_private_response(
    read_history: bool, identity_engine: AsyncEngine
) -> None:
    api = await prepared(identity_engine)

    async def fail(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        raise StorageUnavailableError

    uow = replace(api.uow, recorder=fail)
    operation = (
        ReadOperatorRequestHistory(uow, HASHER, CODEC)(
            api.owner.credential, api.sender.id, api.request.id
        )
        if read_history
        else ReadOperatorRequests(uow, HASHER, FINGERPRINTER, CODEC)(
            api.owner.credential, api.sender.id, OperatorRequestFilters()
        )
    )
    with pytest.raises(StorageUnavailableError):
        await operation
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
        assert not tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        )


async def test_actual_final_session_expiry_after_audit_rolls_back(
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

    async def expire(session: AsyncSession, audit: OperatorAudit) -> None:
        nonlocal entered
        await record_operator_audit(session, audit)
        entered = True
        await session.execute(select(func.pg_sleep(1.1)))

    with pytest.raises(UnauthenticatedError):
        await ReadOperatorRequestHistory(replace(api.uow, recorder=expire), HASHER, CODEC)(
            api.owner.credential, api.sender.id, api.request.id
        )
    assert entered
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))


async def test_cancelled_inspection_rolls_back_and_releases_auth_locks(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def paused(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        entered.set()
        await release.wait()

    task = asyncio.create_task(
        ReadOperatorRequestHistory(replace(api.uow, recorder=paused), HASHER, CODEC)(
            api.owner.credential, api.sender.id, api.request.id
        )
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
            api.history()(api.owner.credential, api.sender.id, api.request.id), timeout=5
        )
        is not None
    )


async def test_sql_source_methods_require_current_operator_authority(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    async with api.uow.sessions() as session:
        with pytest.raises(RuntimeError, match="operator"):
            await SqlOperatorRequestTransaction(session, record_operator_audit).request_account(
                api.sender.id
            )
