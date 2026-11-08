from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.requests.queries import ListRequests, ReadRequest
from studymate.application.requests.viewing import AcknowledgeRequestViewed
from studymate.infrastructure.persistence.product_events import record_request_viewed
from studymate.infrastructure.requests.cursors import FernetRequestCursorCodec
from studymate.infrastructure.requests.queries import SqlRequestQueryUnitOfWork
from studymate.infrastructure.requests.viewing import SqlRequestViewUnitOfWork
from studymate.infrastructure.security.browser_tokens import HmacBrowserTokenSigner
from studymate.presentation.browser import SESSION_COOKIE, BrowserConfiguration
from studymate.presentation.request_errors import validation_problem
from studymate.presentation.requests.router import RequestHttpServices, requests_router
from tests.integration.requests.fixture import FINGERPRINTER, HASHER, Services, prepared, sent
from tests.integration.student_actor import Actor

pytestmark = pytest.mark.integration
ORIGIN = "https://requests.test"
SIGNER = HmacBrowserTokenSigner(b"x" * 32)


@asynccontextmanager
async def client(api: Services, actor: Actor) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    query = SqlRequestQueryUnitOfWork(api.sessions)
    app.include_router(
        requests_router(
            RequestHttpServices(
                api.preview,
                api.send,
                api.accept,
                api.decline,
                api.undo,
                api.withdraw,
                ListRequests(query, HASHER, FernetRequestCursorCodec.from_key(b"x" * 32)),
                ReadRequest(query, HASHER),
                AcknowledgeRequestViewed(
                    SqlRequestViewUnitOfWork(api.sessions, record_request_viewed),
                    HASHER,
                    FINGERPRINTER,
                ),
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
            cookies={SESSION_COOKIE: actor.credential.value},
        ) as http,
    ):
        http.headers.update(
            {
                "Origin": ORIGIN,
                "X-CSRF-Token": await SIGNER.csrf_token(actor.credential),
                "Idempotency-Key": str(uuid4()),
            }
        )
        yield http


async def test_real_http_preview_send_read_view_decline_undo_accept_and_recovery(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    async with client(api, sender) as outgoing:
        preview = await outgoing.post(
            "/api/v1/requests/preview", json={"person_id": str(recipient.id), "mode": "find_help"}
        )
        assert preview.status_code == HTTPStatus.OK, preview.text
        assert preview.json()["outcome"] == "preview"
        outgoing.headers["Idempotency-Key"] = str(uuid4())
        body = {
            "person_id": str(recipient.id),
            "preview_id": preview.json()["preview_id"],
            "text": "Explicit reviewed private text",
            "note": "Separate private note",
        }
        sent = await outgoing.post("/api/v1/requests", json=body)
        assert sent.status_code == HTTPStatus.OK, sent.text
        assert sent.json()["outcome"] == "sent"
        assert (await outgoing.post("/api/v1/requests", json=body)).json() == sent.json()
        request_id = sent.json()["request_id"]
        async with client(api, recipient) as incoming:
            detail = await incoming.get(f"/api/v1/requests/{request_id}")
            assert detail.status_code == HTTPStatus.OK, detail.text
            assert detail.json()["request"]["unread"]
            assert detail.json()["text"] == body["text"]
            viewed = await incoming.post(
                f"/api/v1/requests/{request_id}/viewed",
                json={"disclosure_id": detail.json()["disclosure_id"]},
            )
            assert viewed.status_code == HTTPStatus.OK, viewed.text
            listed = await incoming.get("/api/v1/requests?box=received")
            assert listed.status_code == HTTPStatus.OK, listed.text
            assert not listed.json()["requests"][0]["unread"]
            assert listed.json()["unread_received"] == 0
            assert listed.json()["requests"][0]["text"] == body["text"]
            assert listed.json()["requests"][0]["note"] == body["note"]
            assert listed.json()["requests"][0]["subject_label"]
            incoming.headers["Idempotency-Key"] = str(uuid4())
            declined = await incoming.post(
                f"/api/v1/requests/{request_id}/decline",
                json={"person_id": str(sender.id), "expected_version": sent.json()["version"]},
            )
            assert declined.status_code == HTTPStatus.OK, declined.text
            assert declined.json()["undo_until"] is not None
            incoming.headers["Idempotency-Key"] = str(uuid4())
            undone = await incoming.post(
                f"/api/v1/requests/{request_id}/undo-decline",
                json={"person_id": str(sender.id), "expected_version": declined.json()["version"]},
            )
            assert undone.status_code == HTTPStatus.OK, undone.text
            incoming.headers["Idempotency-Key"] = str(uuid4())
            accepted = await incoming.post(
                f"/api/v1/requests/{request_id}/accept",
                json={"person_id": str(sender.id), "expected_version": undone.json()["version"]},
            )
            assert accepted.status_code == HTTPStatus.OK, accepted.text
            assert accepted.json()["conversation_id"] is not None
            assert accepted.headers["cache-control"] == "no-store"
        outgoing.headers["Idempotency-Key"] = str(uuid4())
        connected = await outgoing.post(
            "/api/v1/requests/preview", json={"person_id": str(recipient.id), "mode": "find_help"}
        )
        assert connected.json()["outcome"] == "connected"
        assert connected.json()["conversation_id"] == accepted.json()["conversation_id"]


async def test_http_browser_write_guards_and_strict_private_input_errors(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    async with client(api, sender) as http:
        body = {"person_id": str(recipient.id), "mode": "find_help"}
        http.headers["Origin"] = "https://foreign.test"
        denied = await http.post("/api/v1/requests/preview", json=body)
        assert denied.status_code == HTTPStatus.FORBIDDEN
        http.headers["Origin"] = ORIGIN
        http.headers["X-CSRF-Token"] = "wrong"
        assert (
            await http.post("/api/v1/requests/preview", json=body)
        ).status_code == HTTPStatus.FORBIDDEN
        http.headers["X-CSRF-Token"] = await SIGNER.csrf_token(sender.credential)
        bad = await http.post(
            "/api/v1/requests",
            json={
                "person_id": str(recipient.id),
                "preview_id": str(uuid4()),
                "text": "PRIVATE\x00VALUE",
            },
        )
        assert bad.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert "PRIVATE" not in bad.text
        assert (
            await http.get("/api/v1/requests?box=sent&view=recently_declined")
        ).status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        http.cookies.clear()
        assert (await http.get("/api/v1/requests")).status_code == HTTPStatus.UNAUTHORIZED
        assert (
            await http.post("/api/v1/requests/preview", json=body)
        ).status_code == HTTPStatus.UNAUTHORIZED


async def test_http_ownership_stale_revision_withdrawal_and_original_receipt(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    value = await sent(api, sender, recipient)
    async with client(api, sender) as http:
        detail = await http.get(f"/api/v1/requests/{value.id}")
        assert detail.status_code == HTTPStatus.OK
        assert (await http.get(f"/api/v1/requests/{uuid4()}")).status_code == HTTPStatus.NOT_FOUND
        assert (
            await http.get("/api/v1/requests?cursor=invalid")
        ).status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        wrong = await http.post(
            f"/api/v1/requests/{value.id}/withdraw",
            json={"person_id": str(recipient.id), "expected_version": value.version + 1},
        )
        assert wrong.status_code == HTTPStatus.CONFLICT, wrong.text
        assert wrong.json()["recovery"]["current_version"] == value.version
        http.headers["Idempotency-Key"] = str(uuid4())
        body = {"person_id": str(recipient.id), "expected_version": value.version}
        withdrawn = await http.post(f"/api/v1/requests/{value.id}/withdraw", json=body)
        assert withdrawn.status_code == HTTPStatus.OK, withdrawn.text
        assert withdrawn.json()["outcome"] == "withdrawn"
        assert (
            await http.post(f"/api/v1/requests/{value.id}/withdraw", json=body)
        ).json() == withdrawn.json()
        history = await http.get("/api/v1/requests?box=sent&view=history")
        assert history.status_code == HTTPStatus.OK
        assert history.json()["successful_today"] == 1
        assert history.json()["requests"][0]["state"] == "withdrawn"
        http.headers["Idempotency-Key"] = str(uuid4())
        cooldown = await http.post(
            "/api/v1/requests/preview", json={"person_id": str(recipient.id), "mode": "find_help"}
        )
        assert cooldown.status_code == HTTPStatus.CONFLICT, cooldown.text
        assert cooldown.headers["retry-after"]
        async with client(api, recipient) as other:
            foreign_ack = await other.post(
                f"/api/v1/requests/{value.id}/viewed",
                json={"disclosure_id": detail.json()["disclosure_id"]},
            )
            assert foreign_ack.status_code == HTTPStatus.NOT_FOUND
        http.cookies.clear()
        assert (
            await http.get(f"/api/v1/requests/{value.id}")
        ).status_code == HTTPStatus.UNAUTHORIZED
