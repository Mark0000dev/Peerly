from hashlib import sha256
from http import HTTPStatus
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.chat_images.worker import ChatImageProcessingStep, ProcessNextChatImage
from studymate.infrastructure.chat_images.worker import SqlChatImageWorkerUnitOfWork
from studymate.infrastructure.media.images import BoundedImageProcessor
from studymate.presentation.browser import SESSION_COOKIE
from tests.image_fixture import encoded
from tests.integration.conversation_http_fixture import ConversationHarness, accepted_conversation
from tests.integration.http_identity import BrowserHarness, write_headers

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("caption", [None, "Explicit private caption"])
async def test_real_image_http_pipeline_recovers_source_and_confirms_only_explicit_send(
    browser: BrowserHarness, identity_engine: AsyncEngine, caption: str | None
) -> None:
    owned = await accepted_conversation(browser, identity_engine)
    data = encoded()
    client_id = str(uuid4())
    collection = f"{owned.prefix}/image-preparations"
    body = {
        "client_message_id": client_id,
        "size": len(data),
        "sha256": sha256(data).hexdigest(),
        "content_type": "image/png",
    }
    headers = await write_headers(browser.client)
    started = await browser.client.post(collection, json=body, headers=headers)
    assert started.status_code == HTTPStatus.ACCEPTED, started.text
    image_id = started.json()["image_id"]
    path = f"{collection}/{image_id}"
    await assert_recovered_source(browser, collection, image_id, sha256(data).hexdigest())
    access = await browser.client.post(
        f"{path}/upload-access", headers=await write_headers(browser.client)
    )
    assert access.status_code == HTTPStatus.OK, access.text
    assert access.json()["fields"]
    browser.storage.data = data
    final_headers = await write_headers(browser.client)
    finalized = await browser.client.post(f"{path}/finalize", headers=final_headers)
    assert finalized.status_code == HTTPStatus.ACCEPTED, finalized.text
    processor = BoundedImageProcessor()
    try:
        assert (
            await ProcessNextChatImage(
                SqlChatImageWorkerUnitOfWork(
                    async_sessionmaker(identity_engine, expire_on_commit=False)
                ),
                browser.storage,
                processor,
            )()
            == ChatImageProcessingStep.READY
        )
    finally:
        await processor.close()
    ready = await browser.client.get(path)
    assert ready.status_code == HTTPStatus.OK
    assert ready.json()["state"] == "ready"
    assert ready.json()["message_outcome"] is None
    assert (await browser.client.get(f"{owned.prefix}/messages")).json()["messages"] == []
    assert (
        await browser.client.post(collection, json=body, headers=headers)
    ).json() == started.json()
    assert (
        await browser.client.post(f"{path}/finalize", headers=final_headers)
    ).json() == finalized.json()
    preview = await browser.client.get(f"{path}/display")
    assert preview.status_code == HTTPStatus.OK, preview.text
    assert preview.headers["content-type"] == "image/jpeg"
    send_body = {"client_message_id": client_id, "image_id": image_id, "text": caption}
    send_headers = await write_headers(browser.client)
    sent = await browser.client.post(
        f"{owned.prefix}/messages", json=send_body, headers=send_headers
    )
    assert sent.status_code == HTTPStatus.OK, sent.text
    message = sent.json()["message"]
    assert message["image_id"] == image_id
    assert message["text"] == caption
    assert message["sequence"] == 1
    assert (
        await browser.client.post(f"{owned.prefix}/messages", json=send_body, headers=send_headers)
    ).json() == sent.json()
    assert (await browser.client.get(path)).json()["message_outcome"][
        "attachment_confirmed"
    ] is True
    await assert_participant_display(
        browser, owned, UUID(message["message_id"]), image_id, preview.content
    )


async def assert_recovered_source(
    browser: BrowserHarness, collection: str, image_id: str, fingerprint: str
) -> None:
    recovered = await browser.client.get(collection)
    assert recovered.status_code == HTTPStatus.OK
    preparation = recovered.json()["preparations"][0]
    assert preparation["image_id"] == image_id
    assert preparation["expected_source"]["sha256"] == fingerprint
    assert preparation["message_outcome"] is None


async def assert_participant_display(
    browser: BrowserHarness,
    owned: ConversationHarness,
    message_id: UUID,
    image_id: str,
    expected: bytes,
) -> None:
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, owned.actors.peer.credential.value)
    owner_path = f"{owned.prefix}/image-preparations/{image_id}"
    assert (await browser.client.get(owner_path)).status_code == HTTPStatus.NOT_FOUND
    assert (await browser.client.get(f"{owner_path}/display")).status_code == HTTPStatus.NOT_FOUND
    display = await browser.client.get(f"{owned.prefix}/messages/{message_id}/image")
    assert display.status_code == HTTPStatus.OK, display.text
    assert display.content == expected
    assert display.headers["cache-control"] == "private, no-store"
