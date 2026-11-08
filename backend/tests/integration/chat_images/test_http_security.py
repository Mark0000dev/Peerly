"""Negative real root image contracts; controlled providers and unique migrated schemas."""

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from hashlib import sha256
from http import HTTPStatus
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlalchemy.pool import AsyncAdaptedQueuePool

from studymate.application.media.storage import UploadAccess
from studymate.domain.media import MediaObjectRef
from studymate.infrastructure.chat_images.models import ChatImageRecord
from studymate.infrastructure.persistence.identity_models import SessionRecord
from studymate.infrastructure.persistence.message_models import (
    MessageOperationRecord,
    MessageRecord,
)
from studymate.presentation.browser import SESSION_COOKIE
from tests.image_fixture import encoded
from tests.integration.conversation_http_fixture import ConversationHarness, accepted_conversation
from tests.integration.http_identity import BrowserHarness, write_headers
from tests.integration.media_fixture import Storage

pytestmark = pytest.mark.integration


async def start_image(browser: BrowserHarness, owned: ConversationHarness) -> tuple[UUID, UUID]:
    data = encoded()
    client_id = uuid4()
    response = await browser.client.post(
        f"{owned.prefix}/image-preparations",
        json={
            "client_message_id": str(client_id),
            "size": len(data),
            "sha256": sha256(data).hexdigest(),
            "content_type": "image/png",
        },
        headers=await write_headers(browser.client),
    )
    assert response.status_code == HTTPStatus.ACCEPTED
    return UUID(response.json()["image_id"]), client_id


@pytest.mark.parametrize("endpoint", ["start", "finalize", "upload-access"])
async def test_root_image_commands_bound_media_size_wait_and_body_shape(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
    endpoint: str,
) -> None:
    owned = await accepted_conversation(browser, identity_engine)
    image_id, _client_id = await start_image(browser, owned)
    collection = f"{owned.prefix}/image-preparations"
    path = collection if endpoint == "start" else f"{collection}/{image_id}/{endpoint}"
    headers = await write_headers(browser.client)
    if endpoint == "start":
        unsupported = await browser.client.post(
            path,
            content="{}",
            headers={
                **headers,
                "Content-Type": "text/plain",
            },
        )
        assert unsupported.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    else:
        body = await browser.client.post(path, json={}, headers=headers)
        assert body.status_code == HTTPStatus.BAD_REQUEST
        assert body.json()["code"] == "command_body_rejected"
    oversized = await browser.client.post(
        path,
        content=b"x" * 8193,
        headers={
            **headers,
            "Content-Type": "application/json",
        },
    )
    assert oversized.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE

    async def slow() -> AsyncIterator[bytes]:
        yield b"{"
        await asyncio.Event().wait()

    timeout = await browser.client.post(
        path,
        content=slow(),
        headers={
            **headers,
            "Content-Type": "application/json",
        },
    )
    assert timeout.status_code == HTTPStatus.REQUEST_TIMEOUT
    async with async_sessionmaker(identity_engine)() as session:
        root = await session.get(ChatImageRecord, image_id)
        assert root is not None
        assert root.current_version == 1
        assert await session.scalar(select(func.count()).select_from(MessageRecord)) == 0


async def test_peer_cannot_resume_finalize_sign_or_preview_another_owners_preparation(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    owned = await accepted_conversation(browser, identity_engine)
    image_id, _client_id = await start_image(browser, owned)
    path = f"{owned.prefix}/image-preparations/{image_id}"
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, owned.actors.peer.credential.value)
    headers = await write_headers(browser.client)
    collection = await browser.client.get(f"{owned.prefix}/image-preparations")
    assert collection.status_code == HTTPStatus.OK
    assert collection.json()["preparations"] == []
    for resource in (path, f"{path}/display"):
        response = await browser.client.get(resource)
        assert response.status_code == HTTPStatus.NOT_FOUND
        assert "expected_source" not in response.text
    for action in ("upload-access", "finalize"):
        response = await browser.client.post(f"{path}/{action}", headers=headers)
        assert response.status_code == HTTPStatus.NOT_FOUND
        assert "storage.example.test" not in response.text
    assert not browser.storage.accesses
    async with async_sessionmaker(identity_engine)() as session:
        root = await session.get(ChatImageRecord, image_id)
        assert root is not None
        assert root.current_version == 1
        assert await session.scalar(select(func.count()).select_from(MessageRecord)) == 0


@pytest.mark.parametrize("unknown", [False, True])
async def test_unknown_or_not_ready_image_send_is_conflict_without_message_or_operation(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
    unknown: bool,
) -> None:
    owned = await accepted_conversation(browser, identity_engine)
    image_id, client_id = await start_image(browser, owned)
    response = await browser.client.post(
        f"{owned.prefix}/messages",
        json={
            "client_message_id": str(client_id),
            "image_id": str(uuid4() if unknown else image_id),
        },
        headers=await write_headers(browser.client),
    )
    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json()["code"] == "message_image_unavailable"
    async with async_sessionmaker(identity_engine)() as session:
        assert await session.scalar(select(func.count()).select_from(MessageRecord)) == 0
        assert await session.scalar(select(func.count()).select_from(MessageOperationRecord)) == 0


async def test_revocation_during_upload_signing_prevents_access_response(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owned = await accepted_conversation(browser, identity_engine)
    image_id, _client_id = await start_image(browser, owned)
    headers = await write_headers(browser.client)
    started, release = asyncio.Event(), asyncio.Event()
    original = Storage.upload_access

    async def paused(
        storage: Storage, reference: MediaObjectRef, content_type: str, expires_at: datetime
    ) -> UploadAccess:
        started.set()
        await release.wait()
        return await original(storage, reference, content_type, expires_at)

    monkeypatch.setattr(Storage, "upload_access", paused)
    task = asyncio.create_task(
        browser.client.post(
            f"{owned.prefix}/image-preparations/{image_id}/upload-access",
            headers=headers,
        )
    )
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        assert isinstance(identity_engine.pool, AsyncAdaptedQueuePool)
        assert identity_engine.pool.checkedout() == 0
        async with async_sessionmaker(identity_engine).begin() as session:
            await session.execute(
                update(SessionRecord)
                .where(SessionRecord.account_id == owned.actors.viewer.id)
                .values(revoked_at=func.clock_timestamp())
            )
        release.set()
        response = await asyncio.wait_for(task, timeout=5)
        assert response.status_code == HTTPStatus.UNAUTHORIZED
        assert "storage.example.test" not in response.text
        assert "fields" not in response.json()
    finally:
        release.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert len(browser.storage.accesses) == 1
