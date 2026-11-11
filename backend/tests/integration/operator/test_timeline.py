"""Actual isolated PostgreSQL timeline proof under paired main0038."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from http import HTTPStatus
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from opentelemetry.sdk.trace import TracerProvider
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.accounts import ReadOperatorAccount
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.timeline import (
    ReadOperatorAudit,
    ReadOperatorEvent,
    SearchOperatorEvents,
)
from studymate.application.operator.timeline_ports import OperatorEventFilters
from studymate.application.profiles.goals import (
    ReadOwnGoal,
    SavedGoal,
    SaveGoalCommand,
    SaveOwnGoal,
)
from studymate.domain.operator.audit import OPERATOR_EVENT_PAGE_SIZE, OperatorAudit
from studymate.domain.operator.timeline import OperatorEventKind
from studymate.domain.study_context import GoalContent
from studymate.infrastructure.observability.http import JsonHttpObserver
from studymate.infrastructure.observability.tracing import OtelHttpTracing
from studymate.infrastructure.operator.models import (
    OperatorAccessRecord,
    OperatorAccessRevisionRecord,
    OperatorAuditRecord,
)
from studymate.infrastructure.operator.timeline_cursors import FernetOperatorEventCursorCodec
from studymate.infrastructure.operator.timeline_transactions import SqlOperatorTimelineUnitOfWork
from studymate.infrastructure.persistence.discovery_freshness_models import DiscoveryExposureRecord
from studymate.infrastructure.persistence.goals import SqlGoalTransaction, SqlGoalUnitOfWork
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import (
    record_operator_audit,
)
from studymate.infrastructure.persistence.transactions import open_transaction
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.timeline_router import (
    OperatorTimelineHttpServices,
    operator_timeline_router,
)
from studymate.presentation.request_correlation import RequestCorrelation
from studymate.presentation.request_errors import validation_problem
from tests.integration.feedback.fixture import FeedbackServices, prepared
from tests.integration.operator.test_reads import operator
from tests.integration.operator.test_reads import uow as account_uow
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.student_actor import Actor

pytestmark = pytest.mark.integration
CODEC = FernetOperatorEventCursorCodec.from_key(b"t" * 32)


def unit(api: FeedbackServices) -> SqlOperatorTimelineUnitOfWork:
    return SqlOperatorTimelineUnitOfWork(api.chat.api.sessions, record_operator_audit)


def search(api: FeedbackServices) -> SearchOperatorEvents:
    return SearchOperatorEvents(unit(api), HASHER, FINGERPRINTER, CODEC)


@asynccontextmanager
async def client(api: FeedbackServices, viewer: Actor) -> AsyncIterator[AsyncClient]:
    provider = TracerProvider()
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.add_middleware(
        RequestCorrelation,
        observer=JsonHttpObserver(),
        tracing=OtelHttpTracing(provider.get_tracer("synthetic-timeline")),
    )
    app.include_router(
        operator_timeline_router(
            OperatorTimelineHttpServices(
                search(api),
                ReadOperatorEvent(unit(api), HASHER),
                ReadOperatorAudit(unit(api), HASHER),
            )
        )
    )
    try:
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="https://operator.test",
                cookies={SESSION_COOKIE: viewer.credential.value},
            ) as http,
        ):
            yield http
    finally:
        provider.shutdown()


async def test_actual_correlated_timeline_and_original_audit_no_private_content_or_activity(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    await api.exchange()
    await api.outcomes()(api.outcome())
    await api.feedback()(api.review())
    viewer = await operator(identity_engine)
    action_id = uuid4()
    async with client(api, viewer) as http:
        http.headers.update(
            {
                "X-Action-ID": str(action_id),
                "traceparent": "00-" + "a" * 32 + "-" + "b" * 16 + "-01",
            }
        )
        initial = await http.get(
            "/api/v1/operator/events",
            params={"subject_account_id": str(api.chat.sender.id), "kind": "feedback.saved"},
        )
        assert initial.status_code == HTTPStatus.OK
        assert len(initial.json()["events"]) == 1
        request_id = UUID(initial.headers["X-Request-ID"])
        async with api.chat.api.sessions() as session:
            original = (
                await session.scalars(
                    select(ProductEventRecord).where(
                        ProductEventRecord.account_id == viewer.id,
                        ProductEventRecord.request_id == request_id,
                    )
                )
            ).one()
            event_id, audit_id = original.id, original.operator_audit_id
            assert audit_id is not None
        response = await http.get(
            "/api/v1/operator/events",
            params={
                "subject_account_id": str(viewer.id),
                "http_request_id": str(request_id),
                "action_id": str(action_id),
                "trace_id": "a" * 32,
                "kind": "operator.inspected",
                "occurred_from": "2020-01-01T00:00:00Z",
                "occurred_before": "2100-01-01T00:00:00Z",
            },
        )
        assert [row["id"] for row in response.json()["events"]] == [str(event_id)]
        detail = await http.get(f"/api/v1/operator/events/{event_id}")
        assert detail.json()["facts"]["operator_action"] == "search_events"
        assert detail.json()["origin"]["trace_id"] == "a" * 32
        inspected = await http.get(f"/api/v1/operator/audits/{audit_id}")
        assert inspected.json()["query_fingerprinted"] is True
        assert inspected.json()["action"] == "search_events"
        for reply in (initial, response, detail, inspected):
            assert reply.status_code == HTTPStatus.OK
            assert reply.headers["Cache-Control"] == "no-store"
            assert reply.headers["Referrer-Policy"] == "no-referrer"
            for private in (
                "Private source content",
                "Synthetic private team note",
                "preserved indentation",
                '"query_fingerprint":',
            ):
                assert private not in reply.text
    async with api.chat.api.sessions() as session:
        assert await session.get(DiscoveryExposureRecord, viewer.id) is None


async def test_detail_missing_is_committed_audit_not_premature404_rollback(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    viewer = await operator(identity_engine)
    async with client(api, viewer) as http:
        for path in (f"/events/{uuid4()}", f"/audits/{uuid4()}"):
            response = await http.get("/api/v1/operator" + path)
            assert response.status_code == HTTPStatus.NOT_FOUND
    async with api.chat.api.sessions() as session:
        rows = tuple(await session.scalars(select(OperatorAuditRecord)))
        assert len(rows) == len(("event", "audit"))
        assert all(row.outcome == "not_found" and not row.result_ids for row in rows)


async def test_historical_audit_retains_original_revoked_grant_while_new_viewer_needs_live_role(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    viewer = await operator(identity_engine)
    await search(api)(
        viewer.credential, OperatorEventFilters(subject_account_id=api.chat.sender.id)
    )
    async with api.chat.api.sessions.begin() as session:
        original = (await session.scalars(select(OperatorAuditRecord))).one()
        original_id = original.id
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        await session.execute(
            select(OperatorAccessRecord)
            .where(OperatorAccessRecord.account_id == viewer.id)
            .with_for_update()
        )
        session.add(
            OperatorAccessRevisionRecord(
                account_id=viewer.id, version=2, active=False, changed_at=now
            )
        )
        await session.flush()
        await session.execute(
            update(OperatorAccessRecord)
            .where(OperatorAccessRecord.account_id == viewer.id)
            .values(current_version=2)
        )
    with pytest.raises(OperatorAccessDeniedError):
        await ReadOperatorAudit(unit(api), HASHER)(viewer.credential, original_id)
    second = await operator(identity_engine)
    detail = await ReadOperatorAudit(unit(api), HASHER)(second.credential, original_id)
    assert detail is not None
    assert detail.audit.access.account_id == viewer.id
    assert detail.audit.access.version == 1
    assert detail.audit.access.active


@pytest.mark.parametrize("operation", ["search", "event", "audit"])
async def test_canonical_failure_rolls_back_new_inspection_and_never_returns_data(
    identity_engine: AsyncEngine, operation: str
) -> None:
    api = await prepared(identity_engine)
    viewer = await operator(identity_engine)
    await ReadOperatorAccount(account_uow(identity_engine), HASHER)(
        viewer.credential, api.chat.sender.id
    )
    async with api.chat.api.sessions() as session:
        original = (await session.scalars(select(OperatorAuditRecord))).one()
        original_id = original.id
        target_event = (
            await session.scalars(
                select(ProductEventRecord)
                .where(ProductEventRecord.account_id == api.chat.sender.id)
                .limit(1)
            )
        ).one()
        event_id = target_event.id
    before = await counts(api)

    async def fail(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        raise RuntimeError("synthetic canonical failure")

    failing = SqlOperatorTimelineUnitOfWork(api.chat.api.sessions, fail)
    with pytest.raises(RuntimeError, match="synthetic canonical failure"):
        await read_with(failing, viewer, operation, event_id, original_id)
    assert await counts(api) == before


async def read_with(
    source: SqlOperatorTimelineUnitOfWork,
    viewer: Actor,
    operation: str,
    event_id: UUID,
    audit_id: UUID,
) -> None:
    if operation == "search":
        await SearchOperatorEvents(source, HASHER, FINGERPRINTER, CODEC)(
            viewer.credential, OperatorEventFilters()
        )
    elif operation == "event":
        await ReadOperatorEvent(source, HASHER)(viewer.credential, event_id)
    else:
        await ReadOperatorAudit(source, HASHER)(viewer.credential, audit_id)


async def counts(api: FeedbackServices) -> tuple[int, int]:
    async with api.chat.api.sessions() as session:
        audits = len(tuple(await session.scalars(select(OperatorAuditRecord))))
        events = len(tuple(await session.scalars(select(ProductEventRecord))))
    return audits, events


async def test_query_cancel_preserves_cancellation_and_releases_role_and_session_locks(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    viewer = await operator(identity_engine)
    async with api.chat.api.sessions() as session:
        event_id = (await session.scalars(select(ProductEventRecord.id).limit(1))).one()
    entered = asyncio.Event()
    release = asyncio.Event()
    before = await counts(api)

    async def pause(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        entered.set()
        await release.wait()

    source = SqlOperatorTimelineUnitOfWork(api.chat.api.sessions, pause)
    task = asyncio.create_task(ReadOperatorEvent(source, HASHER)(viewer.credential, event_id))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
    assert await counts(api) == before
    assert await ReadOperatorEvent(unit(api), HASHER)(viewer.credential, event_id) is not None


async def test_fifty_event_search_is_anchored_not_a_commit_watermark(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    viewer = await operator(identity_engine)
    goal_unit = SqlGoalUnitOfWork(api.chat.api.sessions)
    current = await ReadOwnGoal(goal_unit, HASHER)(api.chat.sender.credential)
    assert current is not None
    save = SaveOwnGoal(goal_unit, HASHER, FINGERPRINTER)
    for index in range(OPERATOR_EVENT_PAGE_SIZE + 2):
        current = await save(
            SaveGoalCommand(
                api.chat.sender.credential,
                GoalContent(current.goal.content.subject, f"Synthetic bounded edit {index}"),
                current.goal.id,
                current.goal.version,
                IntentKey(str(uuid4())),
            )
        )
    entered, release = asyncio.Event(), asyncio.Event()

    delayed = SaveOwnGoal(
        PausedGoalUnitOfWork(api.chat.api.sessions, entered, release), HASHER, FINGERPRINTER
    )
    task = asyncio.create_task(
        delayed(
            SaveGoalCommand(
                api.chat.sender.credential,
                GoalContent(current.goal.content.subject, "Synthetic late commit"),
                current.goal.id,
                current.goal.version,
                IntentKey(str(uuid4())),
            )
        )
    )
    filters = OperatorEventFilters(
        subject_account_id=api.chat.sender.id, kind=OperatorEventKind.GOAL_SAVED
    )
    try:
        await asyncio.wait_for(entered.wait(), 5)
        first = await search(api)(viewer.credential, filters)
        assert len(first.events) == OPERATOR_EVENT_PAGE_SIZE
        assert first.next_cursor is not None
    finally:
        release.set()
        await task
    second = await search(api)(viewer.credential, filters, first.next_cursor)
    late_version = task.result().goal.version
    async with api.chat.api.sessions() as session:
        late = (
            await session.scalars(
                select(ProductEventRecord).where(
                    ProductEventRecord.account_id == api.chat.sender.id,
                    ProductEventRecord.kind == "goal.saved",
                    ProductEventRecord.goal_version == late_version,
                )
            )
        ).one()
        late_id = late.id
        assert late.occurred_at <= first.search_anchor_at
        audit_rows = tuple(await session.scalars(select(OperatorAuditRecord)))
        assert all(len(row.result_ids) <= OPERATOR_EVENT_PAGE_SIZE for row in audit_rows)
    # Late commit above the visited position: anchored search is not a replay stream.
    assert late_id not in {row.id for row in first.events + second.events}
    refreshed = await search(api)(viewer.credential, filters)
    assert late_id in {row.id for row in refreshed.events}


@dataclass(frozen=True, slots=True)
class PausedGoalTransaction(SqlGoalTransaction):
    entered: asyncio.Event
    release: asyncio.Event

    async def save_goal(self, goal: SavedGoal) -> None:
        await SqlGoalTransaction.save_goal(self, goal)
        self.entered.set()
        await self.release.wait()


@dataclass(frozen=True, slots=True)
class PausedGoalUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    entered: asyncio.Event
    release: asyncio.Event

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[PausedGoalTransaction]:
        async with open_transaction(self.sessions) as session:
            yield PausedGoalTransaction(session, self.entered, self.release)


@pytest.mark.parametrize(
    "fault", ["search51", "search_no_hmac", "event_wrong_ref", "audit_wrong_kind", "notfound_data"]
)
async def test_actual38_constraints_reject_fabricated_timeline_audit_shapes(
    identity_engine: AsyncEngine, fault: str
) -> None:
    api = await prepared(identity_engine)
    viewer = await operator(identity_engine)
    requested = uuid4()
    searching = fault.startswith("search")
    action = (
        "search_events"
        if searching
        else "read_event"
        if fault == "event_wrong_ref"
        else "read_audit"
    )
    resource = "event" if action != "read_audit" or fault == "audit_wrong_kind" else "audit"
    results = (
        [uuid4() for _ in range(OPERATOR_EVENT_PAGE_SIZE + 1)]
        if fault == "search51"
        else []
        if searching
        else [uuid4() if fault == "event_wrong_ref" else requested]
    )
    async with api.chat.api.sessions() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        row = OperatorAuditRecord(
            id=uuid4(),
            operator_id=viewer.id,
            operator_access_version=1,
            operator_access_active=True,
            action=action,
            resource_kind=resource,
            requested_id=None if searching else requested,
            result_ids=results,
            outcome="search" if searching else "not_found" if fault == "notfound_data" else "read",
            query_fingerprint=b"h" * 32 if searching and fault != "search_no_hmac" else None,
            occurred_at=now,
        )
        session.add(row)
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()
    async with api.chat.api.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))


async def test_final_session_deadline_after_real_canonical_audit_rolls_back_data_response(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    viewer = await operator(identity_engine)
    async with api.chat.api.sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        await session.execute(
            update(SessionRecord)
            .where(SessionRecord.account_id == viewer.id)
            .values(expires_at=now + timedelta(seconds=1))
        )
        event_id = (await session.scalars(select(ProductEventRecord.id).limit(1))).one()
    entered = asyncio.Event()
    before = await counts(api)

    async def delayed(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        entered.set()
        await session.execute(select(func.pg_sleep(1.1)))

    source = SqlOperatorTimelineUnitOfWork(api.chat.api.sessions, delayed)
    with pytest.raises(UnauthenticatedError):
        await ReadOperatorEvent(source, HASHER)(viewer.credential, event_id)
    assert entered.is_set()
    assert await counts(api) == before


async def test_retained_subject_history_is_not_filtered_by_student_visibility_or_lifecycle(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    viewer = await operator(identity_engine)
    filters = OperatorEventFilters(
        subject_account_id=api.chat.sender.id, kind=OperatorEventKind.GOAL_SAVED
    )
    first = await search(api)(viewer.credential, filters)
    async with api.chat.api.sessions.begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == api.chat.sender.id)
            .values(banned_at=func.clock_timestamp(), deleted_at=func.clock_timestamp())
        )
    retained = await search(api)(viewer.credential, filters)
    assert retained.events == first.events
    assert first.events
