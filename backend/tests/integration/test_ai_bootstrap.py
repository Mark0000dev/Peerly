"""Actual application composition; no executor is enabled by this boundary."""

import asyncio
from http import HTTPStatus
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.infrastructure.ai.models import AiJobRecord
from tests.integration.http_identity import BrowserHarness, verified, write_headers

pytestmark = pytest.mark.integration


def draft() -> dict[str, object]:
    return {
        "kind": "clarify_goal",
        "source": {"kind": "draft", "id": str(uuid4()), "version": 1},
        "text": "Understand vectors",
        "target": "context",
    }


async def test_actual_app_authenticates_disabled_ai_without_admission(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    client = browser.client
    unauthenticated = await client.post(
        "/api/v1/ai/jobs",
        json=draft(),
        headers={
            "Idempotency-Key": str(uuid4()),
        },
    )
    assert unauthenticated.status_code == HTTPStatus.UNAUTHORIZED
    await verified(browser, identity_engine)
    response = await client.post(
        "/api/v1/ai/jobs", json=draft(), headers=await write_headers(client)
    )
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json()["code"] == "ai_unavailable"
    assert response.headers["retry-after"] == "1"
    assert response.headers["x-request-id"] == response.json()["request_id"]
    assert response.headers["cache-control"] == "no-store"
    async with async_sessionmaker(identity_engine)() as session:
        assert await session.scalar(select(func.count()).select_from(AiJobRecord)) == 0
    missing = await client.get(f"/api/v1/ai/jobs/{uuid4()}")
    assert missing.status_code == HTTPStatus.NOT_FOUND
    cancelled = await client.post(
        f"/api/v1/ai/jobs/{uuid4()}/cancel", headers=await write_headers(client)
    )
    assert cancelled.status_code == HTTPStatus.NOT_FOUND


async def test_ai_pool_exhaustion_leaves_core_api_responsive(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    await verified(browser, identity_engine)
    async with browser.ai_engine.connect(), browser.ai_engine.connect():
        pending = asyncio.create_task(browser.client.get(f"/api/v1/ai/jobs/{uuid4()}"))
        core = await asyncio.wait_for(browser.client.get("/api/v1/me"), timeout=1)
        unavailable = await asyncio.wait_for(pending, timeout=3)
    assert core.status_code == HTTPStatus.OK
    assert unavailable.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert unavailable.json()["code"] == "ai_unavailable"
    assert unavailable.headers["retry-after"] == "1"
    assert unavailable.headers["x-request-id"] == unavailable.json()["request_id"]
