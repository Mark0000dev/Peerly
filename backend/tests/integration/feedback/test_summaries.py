import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from http import HTTPStatus
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.discovery.profiles import (
    DiscoveryProfileUnavailableError,
    ReadDiscoveryProfile,
)
from studymate.application.feedback.summaries import (
    ReadOwnFeedbackSummary,
    ReadPublicFeedbackSummary,
)
from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.safety.blocks import ChangeBlockCommand, ChangeOwnBlock
from studymate.domain.feedback.summary import FeedbackSummary
from studymate.infrastructure.feedback.summary_transactions import (
    SqlFeedbackSummaryTransaction,
    SqlFeedbackSummaryUnitOfWork,
)
from studymate.infrastructure.persistence.blocks import SqlBlockUnitOfWork
from studymate.infrastructure.persistence.discovery_profiles import SqlDiscoveryProfileUnitOfWork
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.report_models import ProfileAccessRecord
from studymate.infrastructure.persistence.transactions import open_transaction
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.feedback.summaries import (
    FeedbackSummaryHttpServices,
    feedback_summary_router,
)
from studymate.presentation.request_errors import validation_problem
from tests.integration.feedback.fixture import FeedbackServices, prepared
from tests.integration.profile_lifecycle_fixture import command as visibility_command
from tests.integration.profile_lifecycle_fixture import services as visibility_services
from tests.integration.requests.fixture import FINGERPRINTER, HASHER

pytestmark = pytest.mark.integration


def summaries(api: FeedbackServices) -> FeedbackSummaryHttpServices:
    unit = SqlFeedbackSummaryUnitOfWork(api.chat.api.sessions)
    return FeedbackSummaryHttpServices(
        ReadPublicFeedbackSummary(unit, HASHER), ReadOwnFeedbackSummary(unit, HASHER)
    )


@asynccontextmanager
async def client(
    api: FeedbackServices, *, target_owner: bool = False
) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(feedback_summary_router(summaries(api)))
    owner = api.chat.recipient if target_owner else api.chat.sender
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="https://summary.test",
            cookies={SESSION_COOKIE: owner.credential.value},
        ) as http,
    ):
        yield http


async def test_actual_guard_summary_read_no_disclosure_or_event_and_hidden_own_allowed(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    await api.exchange()
    await api.outcomes()(api.outcome())
    await api.feedback()(api.review())
    async with api.chat.api.sessions() as session:
        before = len(tuple(await session.scalars(select(ProductEventRecord))))
    async with client(api) as http:
        public = await http.get(f"/api/v1/people/{api.chat.recipient.id}/feedback-summary")
        assert public.status_code == HTTPStatus.OK
        assert public.json() == {"state": "building", "responses": 1, "publicly_visible": True}
        assert "yes" not in public.json()
        assert public.headers["Cache-Control"] == "no-store"
    async with api.chat.api.sessions() as session:
        assert not tuple(await session.scalars(select(ProfileAccessRecord)))
        assert len(tuple(await session.scalars(select(ProductEventRecord)))) == before
    hide, _ = visibility_services(identity_engine)
    await hide(visibility_command(api.chat.recipient))
    async with client(api) as http:
        unavailable = await http.get(f"/api/v1/people/{api.chat.recipient.id}/feedback-summary")
        assert unavailable.status_code == HTTPStatus.NOT_FOUND
        assert "responses" not in unavailable.json()
    async with client(api, target_owner=True) as http:
        own = await http.get("/api/v1/me/feedback-summary")
        assert own.status_code == HTTPStatus.OK
        assert own.json() == {"state": "building", "responses": 1, "publicly_visible": False}
    retained = await api.read_feedback()(api.chat.sender.credential, api.chat.conversation_id)
    assert retained is not None


@pytest.mark.parametrize("fault", ["blocked", "banned", "deleted", "unknown"])
async def test_public_summary_neutral_unavailable_and_old_context_is_not_authority(
    identity_engine: AsyncEngine, fault: str
) -> None:
    api = await prepared(identity_engine)
    previous = await ReadDiscoveryProfile(
        SqlDiscoveryProfileUnitOfWork(api.chat.api.sessions), HASHER
    )(api.chat.sender.credential, api.chat.recipient.id)
    target_id = api.chat.recipient.id
    if fault == "blocked":
        await ChangeOwnBlock(SqlBlockUnitOfWork(api.chat.api.sessions), HASHER, FINGERPRINTER)(
            ChangeBlockCommand(
                api.chat.sender.credential,
                target_id,
                True,
                0,
                IntentKey(str(uuid4())),
                previous.access_context.id,
            )
        )
    elif fault in {"banned", "deleted"}:
        async with api.chat.api.sessions.begin() as session:
            await session.execute(
                update(AccountRecord)
                .where(AccountRecord.id == target_id)
                .values(
                    banned_at=func.clock_timestamp() if fault == "banned" else None,
                    deleted_at=func.clock_timestamp() if fault == "deleted" else None,
                )
            )
    else:
        target_id = uuid4()
    async with client(api) as http:
        response = await http.get(
            f"/api/v1/people/{target_id}/feedback-summary?context_id={previous.access_context.id}"
        )
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()["code"] == "person_unavailable"
    assert "responses" not in response.json()


@dataclass(frozen=True, slots=True, kw_only=True)
class PausedSummaryTransaction(SqlFeedbackSummaryTransaction):
    entered: asyncio.Event
    release: asyncio.Event

    async def feedback_summary(self, target_id: UUID) -> FeedbackSummary:
        self.entered.set()
        await self.release.wait()
        return await SqlFeedbackSummaryTransaction.feedback_summary(self, target_id)


@dataclass(frozen=True, slots=True)
class PausedSummaryUnitOfWork:
    api: FeedbackServices
    entered: asyncio.Event
    release: asyncio.Event

    @asynccontextmanager
    async def transaction(self, target_id: UUID | None) -> AsyncIterator[PausedSummaryTransaction]:
        async with open_transaction(self.api.chat.api.sessions) as session:
            yield PausedSummaryTransaction(
                session, target_id, entered=self.entered, release=self.release
            )


@pytest.mark.parametrize("mutation", ["hide", "block"])
async def test_public_guard_and_aggregate_remain_locked_against_concurrent_privacy_write(
    identity_engine: AsyncEngine, mutation: str
) -> None:
    api = await prepared(identity_engine)
    source = await ReadDiscoveryProfile(
        SqlDiscoveryProfileUnitOfWork(api.chat.api.sessions), HASHER
    )(api.chat.sender.credential, api.chat.recipient.id)
    entered, release, started = asyncio.Event(), asyncio.Event(), asyncio.Event()
    reading = ReadPublicFeedbackSummary(PausedSummaryUnitOfWork(api, entered, release), HASHER)

    async def privacy_write() -> None:
        started.set()
        if mutation == "hide":
            hide, _ = visibility_services(identity_engine)
            await hide(visibility_command(api.chat.recipient))
        else:
            await ChangeOwnBlock(SqlBlockUnitOfWork(api.chat.api.sessions), HASHER, FINGERPRINTER)(
                ChangeBlockCommand(
                    api.chat.sender.credential,
                    api.chat.recipient.id,
                    True,
                    0,
                    IntentKey(str(uuid4())),
                    source.access_context.id,
                )
            )

    read_task = asyncio.create_task(reading(api.chat.sender.credential, api.chat.recipient.id))
    writer: asyncio.Task[None] | None = None
    try:
        await asyncio.wait_for(entered.wait(), 5)
        writer = asyncio.create_task(privacy_write())
        await asyncio.wait_for(started.wait(), 5)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(writer), 0.1)
    finally:
        release.set()
        await asyncio.gather(read_task, *(() if writer is None else (writer,)))
    assert read_task.result().publicly_visible
    with pytest.raises(DiscoveryProfileUnavailableError):
        await summaries(api).public(api.chat.sender.credential, api.chat.recipient.id)


@dataclass(frozen=True, slots=True)
class SlowSummaryTransaction(SqlFeedbackSummaryTransaction):
    entered: asyncio.Event = field(kw_only=True)

    async def feedback_summary(self, target_id: UUID) -> FeedbackSummary:
        result = await SqlFeedbackSummaryTransaction.feedback_summary(self, target_id)
        self.entered.set()
        await self.session.execute(select(func.pg_sleep(1.1)))
        return result


@dataclass(frozen=True, slots=True)
class SlowSummaryUnitOfWork:
    api: FeedbackServices
    entered: asyncio.Event

    @asynccontextmanager
    async def transaction(self, target_id: UUID | None) -> AsyncIterator[SlowSummaryTransaction]:
        async with open_transaction(self.api.chat.api.sessions) as session:
            yield SlowSummaryTransaction(session, target_id, entered=self.entered)


async def test_actual_session_deadline_after_aggregate_prevents_public_counts(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    async with api.chat.api.sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        await session.execute(
            update(SessionRecord)
            .where(SessionRecord.account_id == api.chat.sender.id)
            .values(expires_at=now + timedelta(seconds=1))
        )
    entered = asyncio.Event()
    with pytest.raises(UnauthenticatedError):
        await ReadPublicFeedbackSummary(SlowSummaryUnitOfWork(api, entered), HASHER)(
            api.chat.sender.credential, api.chat.recipient.id
        )
    assert entered.is_set()


async def test_unscoped_summary_adapter_cannot_read_an_arbitrary_target(
    identity_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with SqlFeedbackSummaryUnitOfWork(sessions).transaction(None) as transaction:
        with pytest.raises(RuntimeError, match="authenticated SQL scope"):
            await transaction.feedback_summary(uuid4())
