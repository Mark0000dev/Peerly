from dataclasses import replace
from http import HTTPStatus
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.chat_images.worker import ChatImageProcessingStep, ProcessNextChatImage
from studymate.domain.messaging import MessageContent
from studymate.infrastructure.chat_images.worker import SqlChatImageWorkerUnitOfWork
from studymate.infrastructure.media.images import BoundedImageProcessor
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.report_models import ProfileReportRecord
from studymate.presentation.browser import SESSION_COOKIE
from tests.image_fixture import encoded
from tests.integration.http_identity import BrowserHarness, write_headers
from tests.integration.profile_lifecycle_fixture import command as visibility_command
from tests.integration.profile_lifecycle_fixture import services as visibility_services
from tests.integration.test_chat_image_worker import queued
from tests.integration.test_message_commands import Chat

pytestmark = pytest.mark.integration


async def reportable(browser: BrowserHarness, engine: AsyncEngine) -> tuple[Chat, UUID, UUID]:
    browser.storage.data = encoded()
    owned, image = await queued(engine, browser.storage.data)
    processor = BoundedImageProcessor()
    try:
        assert (
            await ProcessNextChatImage(
                SqlChatImageWorkerUnitOfWork(owned.api.sessions), browser.storage, processor
            )()
            == ChatImageProcessingStep.READY
        )
    finally:
        await processor.close()
    result = await owned.send()(
        replace(
            owned.command(),
            client_message_id=image.client_message_id,
            content=MessageContent(image_id=image.id),
        )
    )
    assert result.message is not None
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, owned.recipient.credential.value)
    return owned, image.id, result.message.id


async def test_actual_root_image_report_uses_hidden_chat_source_and_unified_canonical_journal(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    owned, image_id, message_id = await reportable(browser, identity_engine)
    visibility, _ = visibility_services(identity_engine)
    await visibility(visibility_command(owned.sender))
    path = f"/api/v1/conversations/{owned.conversation_id}/messages/{message_id}/report-contexts"
    context = await browser.client.post(path, headers=await write_headers(browser.client))
    assert context.status_code == HTTPStatus.CREATED, context.text
    assert context.json()["message_id"] == str(message_id)
    assert context.json()["image_id"] == str(image_id)
    assert context.json()["kind"] == "message_image"
    body = {
        "kind": "message_image",
        "context_id": context.json()["id"],
        "category": "other",
        "comment": "PRIVATE reviewed image report",
    }
    headers = await write_headers(browser.client)
    response = await browser.client.post("/api/v1/reports", json=body, headers=headers)
    assert response.status_code == HTTPStatus.CREATED, response.text
    assert response.json()["kind"] == "message_image"
    assert response.json()["context_id"] == context.json()["id"]
    assert body["comment"] not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert (
        await browser.client.post("/api/v1/reports", json=body, headers=headers)
    ).json() == response.json()
    async with owned.api.sessions() as session:
        source = await session.get(ProfileReportRecord, UUID(response.json()["id"]))
        assert source is not None
        assert source.kind == "message_image"
        assert source.context_id is None
        assert source.message_context_id == UUID(context.json()["id"])
        assert source.comment == body["comment"]
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProductEventRecord)
                .where(ProductEventRecord.report_id == source.id)
            )
            == 1
        )
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, owned.sender.credential.value)
    assert (
        await browser.client.post(path, headers=await write_headers(browser.client))
    ).status_code == HTTPStatus.NOT_FOUND
    foreign_context = await browser.client.post(
        "/api/v1/reports", json=body, headers=await write_headers(browser.client)
    )
    assert foreign_context.status_code == HTTPStatus.NOT_FOUND


async def test_actual_report_context_body_and_report_kind_are_closed_without_private_echo(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    owned, _, message_id = await reportable(browser, identity_engine)
    path = f"/api/v1/conversations/{owned.conversation_id}/messages/{message_id}/report-contexts"
    headers = await write_headers(browser.client)
    foreign_origin = await browser.client.post(
        path, headers={**headers, "Origin": "https://foreign.invalid"}
    )
    assert foreign_origin.status_code == HTTPStatus.FORBIDDEN
    assert (
        await browser.client.post(path, json={}, headers=headers)
    ).status_code == HTTPStatus.BAD_REQUEST
    assert (
        await browser.client.post(path, content=b"x" * 8193, headers=headers)
    ).status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    issued = await browser.client.post(path, headers=headers)
    assert issued.status_code == HTTPStatus.CREATED
    base = {"kind": "message_image", "context_id": issued.json()["id"], "category": "spam"}
    for extra in ({"actor_id": str(owned.sender.id)}, {"kind": "unknown"}, {"category": "other"}):
        rejected = await browser.client.post(
            "/api/v1/reports", json={**base, **extra}, headers=await write_headers(browser.client)
        )
        assert rejected.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, rejected.text
        assert "input" not in rejected.json()
    mismatched = await browser.client.post(
        "/api/v1/reports",
        json={**base, "kind": "profile"},
        headers=await write_headers(browser.client),
    )
    assert mismatched.status_code == HTTPStatus.NOT_FOUND
    unknown = path.replace(str(message_id), str(uuid4()))
    assert (await browser.client.post(unknown, headers=headers)).status_code == HTTPStatus.NOT_FOUND
    browser.client.cookies.clear()
    assert (await browser.client.post(path, headers=headers)).status_code == HTTPStatus.UNAUTHORIZED
