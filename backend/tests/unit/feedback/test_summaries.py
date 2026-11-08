from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from http import HTTPStatus
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient

from studymate.application.discovery.profiles import DiscoveryProfileUnavailableError
from studymate.application.errors import StorageUnavailableError
from studymate.application.feedback.summaries import (
    ReadOwnFeedbackSummary,
    ReadPublicFeedbackSummary,
)
from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.domain.feedback.summary import FeedbackSummary, summary_from_counts
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.feedback.summaries import (
    FeedbackSummaryHttpServices,
    feedback_summary_router,
)
from studymate.presentation.request_errors import validation_problem
from tests.unit.identity_store import CREDENTIAL
from tests.unit.test_discovery_profiles import TARGET
from tests.unit.test_discovery_profiles import Store as ProfileStore

HASHER = Sha256SessionHasher()


class Store(ProfileStore):
    def __init__(self) -> None:
        super().__init__()
        self.queries: list[UUID] = []
        self.summary = summary_from_counts(1, 1, 1)
        self.expire_on_summary = False
        self.fail_summary = False

    @asynccontextmanager
    async def transaction(self, target_id: UUID | None) -> AsyncIterator["Store"]:
        assert target_id is None or target_id == TARGET
        yield self

    async def feedback_summary(self, target_id: UUID) -> FeedbackSummary:
        self.queries.append(target_id)
        if self.fail_summary:
            raise StorageUnavailableError
        if self.expire_on_summary:
            self.clock = self.actor.session.expires_at
        return self.summary


def public(store: Store) -> ReadPublicFeedbackSummary:
    return ReadPublicFeedbackSummary(store, HASHER)


def own(store: Store) -> ReadOwnFeedbackSummary:
    return ReadOwnFeedbackSummary(store, HASHER)


@asynccontextmanager
async def client(store: Store) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(
        feedback_summary_router(FeedbackSummaryHttpServices(public(store), own(store)))
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="https://summary.test",
            cookies={SESSION_COOKIE: CREDENTIAL.value},
        ) as http,
    ):
        yield http


@pytest.mark.parametrize("denial", ["hidden", "banned", "deleted", "blocked", "missing"])
async def test_public_guard_denies_before_aggregate_query(denial: str) -> None:
    store = Store()
    source = store.sources[TARGET]
    if denial == "hidden":
        assert source.setup.lifecycle is not None
        source = replace(
            source,
            setup=replace(
                source.setup, lifecycle=replace(source.setup.lifecycle, hidden_at=store.clock)
            ),
        )
    elif denial == "banned":
        source = replace(source, banned=True)
    elif denial == "deleted":
        source = replace(source, deleted=True)
    elif denial == "blocked":
        store.blocked = True
    else:
        del store.sources[TARGET]
    if denial != "missing":
        store.sources[TARGET] = source
    with pytest.raises(DiscoveryProfileUnavailableError):
        await public(store)(CREDENTIAL, TARGET)
    assert not store.queries
    assert not store.contexts


async def test_public_count_true_and_own_hidden_is_readable_with_visibility_false() -> None:
    store = Store()
    visible = await public(store)(CREDENTIAL, TARGET)
    assert visible.publicly_visible
    actor_id = store.actor.session.account_id
    source = store.sources[actor_id]
    assert source.setup.lifecycle is not None
    store.sources[actor_id] = replace(
        source,
        setup=replace(
            source.setup, lifecycle=replace(source.setup.lifecycle, hidden_at=store.clock)
        ),
    )
    private = await own(store)(CREDENTIAL)
    assert not private.publicly_visible
    assert private.summary == visible.summary
    assert store.queries == [TARGET, actor_id]
    assert not store.contexts
    with pytest.raises(StudentActionDeniedError):
        await public(store)(CREDENTIAL, TARGET)


@pytest.mark.parametrize("reader", ["public", "own"])
async def test_final_session_expiry_cannot_return_counts(reader: str) -> None:
    store = Store()
    store.expire_on_summary = True
    with pytest.raises(UnauthenticatedError):
        await read(store, reader)


async def read(store: Store, reader: str) -> None:
    if reader == "own":
        await own(store)(CREDENTIAL)
    else:
        await public(store)(CREDENTIAL, TARGET)


async def test_wrong_owned_source_never_returns_counts() -> None:
    store = Store()
    actor_id = store.actor.session.account_id
    store.sources[actor_id] = store.sources[TARGET]
    with pytest.raises(RuntimeError, match="source belongs"):
        await own(store)(CREDENTIAL)
    assert not store.queries


async def test_http_exact_denominator_private_headers_and_below_threshold_no_breakdown() -> None:
    store = Store()
    async with client(store) as http:
        available = await http.get(f"/api/v1/people/{TARGET}/feedback-summary")
        assert available.status_code == HTTPStatus.OK
        assert available.json() == {
            "state": "available",
            "responses": 3,
            "yes": 1,
            "maybe": 1,
            "no": 1,
            "publicly_visible": True,
        }
        store.summary = summary_from_counts(1, 0, 0)
        building = await http.get("/api/v1/me/feedback-summary")
        assert building.json() == {"state": "building", "responses": 1, "publicly_visible": True}
        for response in (available, building):
            assert response.headers["Cache-Control"] == "no-store"
            assert response.headers["Referrer-Policy"] == "no-referrer"
            for forbidden in ("reviewer_id", "team_note", "reason", "operator_id", "storage_key"):
                assert forbidden not in response.text
        assert not store.contexts


@pytest.mark.parametrize(
    "path", [f"/api/v1/people/{TARGET}/feedback-summary", "/api/v1/me/feedback-summary"]
)
async def test_cookie_denial_storage_error_safe_and_not_fake_counts(path: str) -> None:
    store = Store()
    async with client(store) as http:
        http.cookies.clear()
        missing = await http.get(path)
        assert missing.status_code == HTTPStatus.UNAUTHORIZED
        http.cookies.set(SESSION_COOKIE, CREDENTIAL.value)
        store.fail_summary = True
        failed = await http.get(path)
        assert failed.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert failed.headers["Retry-After"] == "1"
        assert "responses" not in failed.json()


async def test_http_public_hidden_neutral404_and_own_unactivated403() -> None:
    store = Store()
    store.blocked = True
    async with client(store) as http:
        denied = await http.get(f"/api/v1/people/{TARGET}/feedback-summary")
        assert denied.status_code == HTTPStatus.NOT_FOUND
        assert denied.json()["code"] == "person_unavailable"
        store.actor = replace(store.actor, activation_complete=False)
        own_denied = await http.get("/api/v1/me/feedback-summary")
        assert own_denied.status_code == HTTPStatus.FORBIDDEN
    assert not store.queries
