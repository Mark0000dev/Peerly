import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.messaging.history import ReadMessageHistory
from studymate.application.messaging.participants import ReadChatAvatar, ReadChatParticipant
from studymate.domain.media import MediaObjectKind, MediaObjectRef
from studymate.infrastructure.messaging.cursors import FernetMessageHistoryCursorCodec
from studymate.infrastructure.messaging.history import SqlMessageHistoryUnitOfWork
from studymate.infrastructure.persistence.message_models import (
    MessageOperationRecord,
    MessageRecord,
)
from studymate.infrastructure.persistence.messaging import SqlMessageUnitOfWork
from studymate.infrastructure.persistence.product_events import record_message_outcome
from studymate.infrastructure.security.browser_tokens import HmacBrowserTokenSigner
from studymate.presentation.browser import SESSION_COOKIE, BrowserConfiguration
from studymate.presentation.messaging.router import MessagingHttpServices, messaging_router
from studymate.presentation.request_errors import validation_problem
from tests.integration.profile_lifecycle_fixture import command as visibility_command
from tests.integration.profile_lifecycle_fixture import services as visibility_services
from tests.integration.requests.fixture import HASHER
from tests.integration.test_message_commands import Chat, chat

pytestmark = pytest.mark.integration
ORIGIN = "https://messaging.test"
SIGNER = HmacBrowserTokenSigner(b"x" * 32)
AVATAR = b"\xff\xd8synthetic processed JPEG\xff\xd9"


class AvatarReader:
    async def read(self, reference: MediaObjectRef) -> bytes:
        assert reference.kind == MediaObjectKind.DISPLAY
        return AVATAR


@asynccontextmanager
async def client(context: Chat) -> AsyncIterator[AsyncClient]:
    uow = SqlMessageUnitOfWork(context.api.sessions, record_message_outcome)
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(
        messaging_router(
            MessagingHttpServices(
                ReadMessageHistory(
                    SqlMessageHistoryUnitOfWork(context.api.sessions, record_message_outcome),
                    HASHER,
                    FernetMessageHistoryCursorCodec.from_key(b"x" * 32),
                ),
                context.send(),
                context.cancel(),
                context.read(),
                ReadChatParticipant(uow, HASHER),
                ReadChatAvatar(uow, HASHER, AvatarReader()),
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
            cookies={SESSION_COOKIE: context.sender.credential.value},
        ) as http,
    ):
        http.headers.update(
            {
                "Origin": ORIGIN,
                "X-CSRF-Token": await SIGNER.csrf_token(context.sender.credential),
                "Idempotency-Key": str(uuid4()),
            }
        )
        yield http


async def test_http_text_send_history_replay_and_truthful_cancel_outcome(
    identity_engine: AsyncEngine,
) -> None:
    context = await chat(identity_engine)
    prefix = f"/api/v1/conversations/{context.conversation_id}"
    client_id = str(uuid4())
    body = {"client_message_id": client_id, "text": "  Exact private text\n second line  "}
    async with client(context) as http:
        lookup = await http.get(f"{prefix}/message-operations/{client_id}")
        assert lookup.status_code == HTTPStatus.OK
        assert lookup.json()["outcome"] == "unobserved"
        assert "not_sent" not in lookup.text
        sent = await http.post(f"{prefix}/messages", json=body)
        assert sent.status_code == HTTPStatus.OK, sent.text
        assert sent.json()["outcome"] == "confirmed"
        assert sent.json()["message"]["text"] == body["text"]
        assert (await http.post(f"{prefix}/messages", json=body)).json() == sent.json()
        assert (await http.get(f"{prefix}/message-operations/{client_id}")).json() == sent.json()
        http.headers["Idempotency-Key"] = str(uuid4())
        cancel = await http.post(f"{prefix}/message-operations/{client_id}/cancel")
        assert cancel.status_code == HTTPStatus.OK, cancel.text
        assert cancel.json() == sent.json()
        history = await http.get(f"{prefix}/messages")
        assert history.status_code == HTTPStatus.OK
        assert history.json()["messages"] == [sent.json()["message"]]
        assert "unread" not in history.json()
        assert history.headers["cache-control"] == "private, no-store"
        http.headers["Idempotency-Key"] = str(uuid4())
        changed = await http.post(
            f"{prefix}/messages", json={**body, "text": "Changed private text"}
        )
        assert changed.status_code == HTTPStatus.CONFLICT
        assert "private text" not in changed.text
        async with context.api.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(MessageRecord)) == 1


async def test_http_cancel_before_send_and_send_cancel_race_use_actual_terminal_root(
    identity_engine: AsyncEngine,
) -> None:
    context = await chat(identity_engine)
    prefix = f"/api/v1/conversations/{context.conversation_id}"
    client_id = str(uuid4())
    async with client(context) as http:
        cancelled = await http.post(f"{prefix}/message-operations/{client_id}/cancel")
        assert cancelled.status_code == HTTPStatus.OK, cancelled.text
        assert cancelled.json()["outcome"] == "cancelled"
        http.headers["Idempotency-Key"] = str(uuid4())
        delayed = await http.post(
            f"{prefix}/messages",
            json={"client_message_id": client_id, "text": "Explicit delayed send"},
        )
        assert delayed.json() == cancelled.json()
        race_id = str(uuid4())
        send, cancel = await asyncio.gather(
            http.post(
                f"{prefix}/messages",
                json={"client_message_id": race_id, "text": "Explicit raced send"},
                headers={"Idempotency-Key": str(uuid4())},
            ),
            http.post(
                f"{prefix}/message-operations/{race_id}/cancel",
                headers={"Idempotency-Key": str(uuid4())},
            ),
        )
        assert send.status_code == cancel.status_code == HTTPStatus.OK
        assert send.json() == cancel.json()
        assert send.json()["outcome"] in {"confirmed", "cancelled"}
        async with context.api.sessions() as session:
            expected_roots = 2
            assert (
                await session.scalar(select(func.count()).select_from(MessageOperationRecord))
                == expected_roots
            )


async def test_http_accepted_participant_avatar_survive_hide_without_discovery_grant(
    identity_engine: AsyncEngine,
) -> None:
    context = await chat(identity_engine)
    prefix = f"/api/v1/conversations/{context.conversation_id}"
    visibility, _ = visibility_services(identity_engine)
    await visibility(visibility_command(context.recipient))
    async with client(context) as http:
        participant = await http.get(f"{prefix}/participant")
        assert participant.status_code == HTTPStatus.OK, participant.text
        assert participant.json()["state"] == "available"
        assert participant.json()["display_name"]
        photo = participant.json()["photo_version"]
        avatar = await http.get(f"{prefix}/participant/avatar/{photo}")
        assert avatar.status_code == HTTPStatus.OK, avatar.text
        assert avatar.content == AVATAR
        assert avatar.headers["content-type"] == "image/jpeg"
        assert avatar.headers["x-content-type-options"] == "nosniff"
        assert (
            await http.get(f"{prefix}/participant/avatar/{photo + 1}")
        ).status_code == HTTPStatus.NOT_FOUND
        assert "storage" not in participant.text


async def test_http_message_source_empty_cancel_and_browser_auth_guards(
    identity_engine: AsyncEngine,
) -> None:
    context = await chat(identity_engine)
    prefix = f"/api/v1/conversations/{context.conversation_id}"
    client_id = str(uuid4())
    async with client(context) as http:
        rejected = await http.post(
            f"{prefix}/messages",
            json={"client_message_id": client_id, "text": "Private text", "image_id": str(uuid4())},
        )
        assert rejected.status_code == HTTPStatus.CONFLICT
        assert rejected.json()["code"] == "message_image_unavailable"
        assert "Private text" not in rejected.text
        injected = await http.post(
            f"{prefix}/messages",
            json={
                "client_message_id": client_id,
                "text": "Private text",
                "actor_id": str(context.recipient.id),
            },
        )
        assert injected.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert "Private text" not in injected.text
        assert (
            await http.post(f"{prefix}/message-operations/{client_id}/cancel", content=b"null")
        ).status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        http.headers["Origin"] = "https://foreign.test"
        assert (
            await http.post(
                f"{prefix}/messages", json={"client_message_id": client_id, "text": "Reviewed"}
            )
        ).status_code == HTTPStatus.FORBIDDEN
        http.headers["Origin"] = ORIGIN
        http.headers["X-CSRF-Token"] = "invalid"
        assert (
            await http.post(f"{prefix}/message-operations/{client_id}/cancel")
        ).status_code == HTTPStatus.FORBIDDEN
        http.headers["X-CSRF-Token"] = await SIGNER.csrf_token(context.sender.credential)
        assert (
            await http.get(f"{prefix}/messages?cursor=invalid")
        ).status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert (
            await http.get(f"/api/v1/conversations/{uuid4()}/messages")
        ).status_code == HTTPStatus.NOT_FOUND
        for path in (
            f"/api/v1/conversations/{uuid4()}/participant",
            f"/api/v1/conversations/{uuid4()}/participant/avatar/1",
            f"/api/v1/conversations/{uuid4()}/message-operations/{client_id}",
        ):
            assert (await http.get(path)).status_code == HTTPStatus.NOT_FOUND
        assert (
            await http.post(
                f"/api/v1/conversations/{uuid4()}/message-operations/{client_id}/cancel"
            )
        ).status_code == HTTPStatus.NOT_FOUND
        http.cookies.clear()
        assert (
            await http.post(f"{prefix}/message-operations/{client_id}/cancel")
        ).status_code == HTTPStatus.UNAUTHORIZED
        for path in (
            f"{prefix}/messages",
            f"{prefix}/participant",
            f"{prefix}/participant/avatar/1",
            f"{prefix}/message-operations/{client_id}",
        ):
            assert (await http.get(path)).status_code == HTTPStatus.UNAUTHORIZED
        assert (
            await http.post(
                f"{prefix}/messages", json={"client_message_id": client_id, "text": "Reviewed"}
            )
        ).status_code == HTTPStatus.UNAUTHORIZED


async def test_operation_lookup_and_cancel_are_own_author_not_peer_client_id(
    identity_engine: AsyncEngine,
) -> None:
    context = await chat(identity_engine)
    peer_command = context.command(context.recipient)
    actual = await context.send()(peer_command)
    prefix = f"/api/v1/conversations/{context.conversation_id}"
    async with client(context) as http:
        own_lookup = await http.get(f"{prefix}/message-operations/{peer_command.client_message_id}")
        assert own_lookup.status_code == HTTPStatus.OK
        assert own_lookup.json()["outcome"] == "unobserved"
        own_cancel = await http.post(
            f"{prefix}/message-operations/{peer_command.client_message_id}/cancel"
        )
        assert own_cancel.status_code == HTTPStatus.OK
        assert own_cancel.json()["outcome"] == "cancelled"
        # Same caller-provided UUID does not grant the other author's operation.
        peer_lookup = await context.read()(
            context.recipient.credential, context.conversation_id, peer_command.client_message_id
        )
        assert peer_lookup == actual
        history = await http.get(f"{prefix}/messages")
        assert history.json()["messages"][0]["author_id"] == str(context.recipient.id)
