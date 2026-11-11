from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from http import HTTPStatus
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from studymate.application.errors import StorageUnavailableError
from studymate.application.feedback.reads import ReadOwnFeedbackContext
from studymate.domain.feedback.assessments import FeedbackRevision
from studymate.infrastructure.feedback.models import PeerFeedbackRecord
from studymate.infrastructure.feedback.transactions import SqlFeedbackUnitOfWork
from studymate.infrastructure.observability.http import JsonHttpObserver
from studymate.infrastructure.observability.tracing import OtelHttpTracing
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.security.browser_tokens import HmacBrowserTokenSigner
from studymate.presentation.browser import SESSION_COOKIE, BrowserConfiguration
from studymate.presentation.feedback.router import FeedbackHttpServices, feedback_router
from studymate.presentation.request_correlation import RequestCorrelation
from studymate.presentation.request_errors import validation_problem
from tests.integration.feedback.fixture import RECORDERS, FeedbackServices, prepared
from tests.integration.feedback.test_commands import counts, make_old_acceptance
from tests.integration.onboarding_fixture import ready_setup
from tests.integration.profile_lifecycle_fixture import complete_existing_setup
from tests.integration.requests.fixture import HASHER
from tests.integration.student_actor import Actor, actor

pytestmark = pytest.mark.integration
ORIGIN = "https://feedback.test"
SIGNER = HmacBrowserTokenSigner(b"x" * 32)


@asynccontextmanager
async def client(api: FeedbackServices, owner: Actor | None = None) -> AsyncIterator[AsyncClient]:
    owner = api.chat.sender if owner is None else owner
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.add_middleware(RequestCorrelation, observer=JsonHttpObserver(), tracing=OtelHttpTracing())
    app.include_router(
        feedback_router(
            FeedbackHttpServices(
                api.outcomes(),
                api.read_outcome(),
                api.feedback(),
                ReadOwnFeedbackContext(api.uow, HASHER),
                api.prompts(),
                SIGNER,
                BrowserConfiguration(ORIGIN, frozenset({ORIGIN})),
            )
        )
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url=ORIGIN,
            cookies={SESSION_COOKIE: owner.credential.value},
        ) as http,
    ):
        http.headers.update(
            {
                "Origin": ORIGIN,
                "X-CSRF-Token": await SIGNER.csrf_token(owner.credential),
                "Idempotency-Key": str(uuid4()),
            }
        )
        yield http


def root(api: FeedbackServices) -> str:
    return f"/api/v1/conversations/{api.chat.conversation_id}"


async def test_real_http_server_eligibility_distinguishes_captured_private_and_new_revision(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    before = await counts(api)
    async with client(api) as http:
        initial = await http.get(root(api) + "/feedback")
        assert initial.json()["can_submit"] is False
        assert initial.json()["submission_publication"] is None
        assert await counts(api) == before
        yes = await http.put(
            root(api) + "/study-outcome", json={"answer": "yes", "expected_version": 0}
        )
        assert yes.status_code == HTTPStatus.OK
        assert (await http.get(root(api) + "/study-outcome")).json()["outcome"] == yes.json()
        ready = await http.get(root(api) + "/feedback")
        assert ready.json()["can_submit"] is True
        assert ready.json()["submission_publication"] == "private_only"
        http.headers["Idempotency-Key"] = str(uuid4())
        body = {
            "again": "maybe",
            "expected_version": 0,
            "team_note": "Synthetic private team input",
        }
        private = await http.put(root(api) + "/feedback", json=body)
        assert private.status_code == HTTPStatus.OK
        assert private.json()["captured_public_eligibility"] is False
        await api.exchange()
        assert (await http.put(root(api) + "/feedback", json=body)).json() == private.json()
        context = await http.get(root(api) + "/feedback")
        assert context.json()["current_publication"] == "private_only"
        assert context.json()["submission_publication"] == "eligible"
        http.headers["Idempotency-Key"] = str(uuid4())
        eligible = await http.put(root(api) + "/feedback", json={**body, "expected_version": 1})
        assert eligible.status_code == HTTPStatus.OK
        assert eligible.json()["captured_public_eligibility"] is True
        assert eligible.json()["id"] == private.json()["id"]
        for response in (initial, yes, ready, private, context, eligible):
            assert response.headers["Cache-Control"] == "no-store"
            assert response.headers["Referrer-Policy"] == "no-referrer"
            for forbidden in (
                "operator_id",
                "removal_reason",
                "storage_key",
                "message_id",
                "secret_digest",
            ):
                assert forbidden not in response.text
    async with api.chat.api.sessions() as session:
        event = (
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "study.reported")
            )
        ).one()
        assert str(event.request_id) == yes.headers["X-Request-ID"]
        assert len(tuple(await session.scalars(select(PeerFeedbackRecord)))) == 1


async def test_http_foreign_and_unknown_conversations_are_neutral404(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    stranger = await actor(identity_engine)
    await ready_setup(identity_engine, stranger.credential)
    await complete_existing_setup(identity_engine, stranger)
    async with client(api, stranger) as http:
        foreign = await http.get(root(api) + "/feedback")
        unknown = await http.get(f"/api/v1/conversations/{uuid4()}/feedback")
        assert foreign.status_code == HTTPStatus.NOT_FOUND
        assert unknown.status_code == HTTPStatus.NOT_FOUND
        assert foreign.json()["code"] == unknown.json()["code"]
    async with api.chat.api.sessions() as session:
        assert not tuple(await session.scalars(select(PeerFeedbackRecord)))


async def test_http_visit_explicit_offered_vs_no_offer_and_no_get_sideeffects(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    await api.exchange()
    async with client(api) as http:
        before = await counts(api)
        await http.get(root(api) + "/feedback")
        await http.get(root(api) + "/study-outcome")
        assert await counts(api) == before
        no_offer = await http.post(root(api) + "/study-prompt-visits", json={})
        assert no_offer.json() == {"outcome": "no_offer"}
        await make_old_acceptance(api)
        assert (
            await http.post(root(api) + "/study-prompt-visits", json={})
        ).json() == no_offer.json()
        http.headers["Idempotency-Key"] = str(uuid4())
        offered = await http.post(root(api) + "/study-prompt-visits", json={})
        assert offered.status_code == HTTPStatus.OK
        assert offered.json()["outcome"] == "offered"
        assert (
            await http.post(root(api) + "/study-prompt-visits", json={})
        ).json() == offered.json()
        http.headers["Idempotency-Key"] = str(uuid4())
        assert (await http.post(root(api) + "/study-prompt-visits", json={})).json() == {
            "outcome": "no_offer"
        }
    async with api.chat.api.sessions() as session:
        events = tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "study.prompt_offered")
            )
        )
        assert len(events) == 1
        assert str(events[0].request_id) == offered.headers["X-Request-ID"]


async def test_http_storage_failure_truthful503_no_private_output_or_partial_commit(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    await api.outcomes()(api.outcome())
    before = await counts(api)

    async def fail(session: AsyncSession, revision: FeedbackRevision) -> None:
        await RECORDERS.assessment(session, revision)
        raise StorageUnavailableError

    failed = replace(
        api, uow=SqlFeedbackUnitOfWork(api.chat.api.sessions, replace(RECORDERS, assessment=fail))
    )
    async with client(failed) as http:
        response = await http.put(
            root(api) + "/feedback",
            json={"again": "yes", "expected_version": 0, "team_note": "Never leak private input"},
        )
        assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert response.headers["Retry-After"] == "1"
        assert "Never leak" not in response.text
        assert await counts(api) == before


async def test_http_deleted_counterpart_keeps_history_but_own_ban_denies_replay(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    async with client(api) as http:
        body = {"answer": "yes", "expected_version": 0}
        original = await http.put(root(api) + "/study-outcome", json=body)
        assert original.status_code == HTTPStatus.OK
        async with api.chat.api.sessions.begin() as session:
            await session.execute(
                update(AccountRecord)
                .where(AccountRecord.id == api.chat.recipient.id)
                .values(deleted_at=func.clock_timestamp())
            )
        retained = await http.get(root(api) + "/feedback")
        assert retained.status_code == HTTPStatus.OK
        assert retained.json()["can_submit"] is True
        async with api.chat.api.sessions.begin() as session:
            await session.execute(
                update(AccountRecord)
                .where(AccountRecord.id == api.chat.sender.id)
                .values(banned_at=func.clock_timestamp())
            )
        denied = await http.put(root(api) + "/study-outcome", json=body)
        assert denied.status_code == HTTPStatus.FORBIDDEN
        assert "outcome" not in denied.json()
