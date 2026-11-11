from datetime import timedelta
from http import HTTPStatus
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.presentation.requests.outputs import PreviewResponse
from tests.integration.discovery_fixture import canonical_goal
from tests.integration.http_identity import BrowserHarness, write_headers
from tests.integration.test_discovery_http import mounted

pytestmark = pytest.mark.integration


async def test_root_composer_keeps_original_preview_but_observes_real_sent_quota_and_pair(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    actors = await mounted(browser, identity_engine)
    body = {"person_id": str(actors.peer.id), "mode": "find_help"}
    headers = await write_headers(browser.client)
    opened = await browser.client.post("/api/v1/requests/preview", json=body, headers=headers)
    assert opened.status_code == HTTPStatus.OK
    original = PreviewResponse.model_validate(opened.json())
    assert original.context.sender_goal is not None
    assert original.context.sender_goal.subject_label in original.suggested_text
    assert original.can_send
    assert original.block_reason is None
    assert original.quota.outgoing_pending == 0
    assert original.quota.successful_today == 0
    assert original.quota.outgoing_pending_remaining == original.quota.outgoing_pending_limit
    assert original.quota.daily_sends_remaining == original.quota.daily_send_limit
    assert original.checked_at < original.quota.reset_at <= original.checked_at + timedelta(days=1)
    local_reset = original.quota.reset_at.astimezone(ZoneInfo("Asia/Kuala_Lumpur"))
    assert (local_reset.hour, local_reset.minute, local_reset.second) == (0, 0, 0)
    sent = await browser.client.post(
        "/api/v1/requests",
        json={
            "person_id": str(actors.peer.id),
            "preview_id": str(original.preview_id),
            "text": "My independently edited invitation",
        },
        headers=await write_headers(browser.client),
    )
    assert sent.status_code == HTTPStatus.OK
    async with async_sessionmaker(identity_engine)() as session:
        events_before = frozenset(await session.scalars(select(ProductEventRecord.id)))
    replay = await browser.client.post("/api/v1/requests/preview", json=body, headers=headers)
    assert replay.status_code == HTTPStatus.OK
    current = PreviewResponse.model_validate(replay.json())
    assert (current.preview_id, current.created_at, current.context, current.suggested_text) == (
        original.preview_id,
        original.created_at,
        original.context,
        original.suggested_text,
    )
    assert not current.can_send
    assert current.block_reason is not None
    assert current.block_reason.value == "existing_outgoing"
    assert current.quota.outgoing_pending == 1
    assert current.quota.successful_today == 1
    assert "My independently edited invitation" not in current.suggested_text
    assert replay.headers["cache-control"] == "no-store"
    async with async_sessionmaker(identity_engine)() as session:
        assert frozenset(await session.scalars(select(ProductEventRecord.id))) == events_before


async def test_root_composer_marks_stale_context_without_replacing_retained_intent(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    actors = await mounted(browser, identity_engine)
    body = {"person_id": str(actors.peer.id), "mode": "find_help"}
    headers = await write_headers(browser.client)
    initial = await browser.client.post("/api/v1/requests/preview", json=body, headers=headers)
    assert initial.status_code == HTTPStatus.OK
    original = PreviewResponse.model_validate(initial.json())
    assert original.context.sender_goal is not None
    await canonical_goal(
        identity_engine,
        actors.viewer,
        original.context.sender_goal.subject_id,
        topic="A different explicitly saved topic",
    )
    refreshed = await browser.client.post("/api/v1/requests/preview", json=body, headers=headers)
    assert refreshed.status_code == HTTPStatus.OK
    current = PreviewResponse.model_validate(refreshed.json())
    assert current.preview_id == original.preview_id
    assert current.context == original.context
    assert current.suggested_text == original.suggested_text
    assert not current.can_send
    assert current.block_reason is not None
    assert current.block_reason.value == "source_changed"
    final = await browser.client.post(
        "/api/v1/requests",
        json={
            "person_id": str(actors.peer.id),
            "preview_id": str(original.preview_id),
            "text": original.suggested_text,
        },
        headers=await write_headers(browser.client),
    )
    assert final.status_code == HTTPStatus.CONFLICT
    assert final.json()["code"] == "request_source_changed"
