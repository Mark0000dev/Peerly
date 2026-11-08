import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from http import HTTPStatus
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from studymate.application.changes.reads import ChangeTransaction, ReadChanges
from studymate.application.errors import StorageUnavailableError
from studymate.domain.changes import ChangeWindow
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.changes.router import ChangeHttpServices, changes_router
from studymate.presentation.changes.stream import ChangeStreamPolicy
from tests.unit.identity_store import CREDENTIAL, IdentityStore


class Store(IdentityStore):
    def __init__(self) -> None:
        super().__init__()
        self.actor = replace(self.actor, activation_complete=True)
        self.reads = 0
        self.storage_failed = False

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[ChangeTransaction]:
        if self.storage_failed:
            raise StorageUnavailableError
        yield self

    async def change_window(self, recipient_id: UUID, after: int | None) -> ChangeWindow:
        assert after in (None, 0)
        self.reads += 1
        if self.reads > 1:
            self.clock = self.actor.session.expires_at
        return ChangeWindow(recipient_id, 0, 0, ())


def application(store: Store) -> FastAPI:
    app = FastAPI()
    app.include_router(
        changes_router(
            ChangeHttpServices(
                ReadChanges(store, Sha256SessionHasher()),
                ChangeStreamPolicy(poll_seconds=0.001),
            )
        )
    )
    return app


@pytest.mark.parametrize(
    ("mode", "status"),
    [
        ("missing", HTTPStatus.UNAUTHORIZED),
        ("cursor", HTTPStatus.UNPROCESSABLE_ENTITY),
        ("expired", HTTPStatus.UNAUTHORIZED),
        ("unactivated", HTTPStatus.FORBIDDEN),
        ("banned", HTTPStatus.FORBIDDEN),
        ("storage", HTTPStatus.SERVICE_UNAVAILABLE),
    ],
)
async def test_sse_authorizes_before_headers_and_preserves_safe_preflight_failures(
    mode: str,
    status: HTTPStatus,
) -> None:
    store = Store()
    if mode == "expired":
        store.clock = store.actor.session.expires_at
    elif mode == "unactivated":
        store.actor = replace(store.actor, activation_complete=False)
    elif mode == "banned":
        store.actor = replace(store.actor, banned=True)
    elif mode == "storage":
        store.storage_failed = True
    cookies = {} if mode == "missing" else {SESSION_COOKIE: CREDENTIAL.value}
    headers = {"Last-Event-ID": "+12"} if mode == "cursor" else {}
    app = application(store)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="https://peerly.test",
            cookies=cookies,
        ) as http,
    ):
        response = await http.get("/api/v1/events", headers=headers)
    assert response.status_code == status
    assert "text/event-stream" not in response.headers["content-type"]
    assert CREDENTIAL.value not in response.text
    if mode == "storage":
        assert response.headers["retry-after"] == "1"


async def test_stream_starts_at_actual_reset_and_closes_after_live_session_expiry() -> None:
    store = Store()
    app = application(store)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="https://peerly.test",
            cookies={SESSION_COOKIE: CREDENTIAL.value},
        ) as http,
        asyncio.timeout(1),
    ):
        response = await http.get("/api/v1/events")
    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text == "id: 0\nevent: reset_required\ndata: {}\n\n"
    assert response.headers["cache-control"] == "private, no-store"
    assert store.reads > 1
    assert set(app.openapi()["paths"]["/api/v1/events"]["get"]["responses"]["200"]["content"]) == {
        "text/event-stream"
    }
