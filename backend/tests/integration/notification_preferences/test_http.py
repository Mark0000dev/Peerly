from http import HTTPStatus

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.integration.http_identity import BrowserHarness, verified, write_headers

pytestmark = pytest.mark.integration


async def test_preference_actual_mount_cas_and_replay(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    await verified(browser, identity_engine)
    path = "/api/v1/me/notification-preference"
    initial = await browser.client.get(path)
    assert initial.status_code == HTTPStatus.OK
    assert initial.json() == {"mode": "messages_and_requests", "version": 0, "changed_at": None}
    headers = await write_headers(browser.client)
    body = {"mode": "all_updates", "expected_version": 0}
    saved = await browser.client.put(path, json=body, headers=headers)
    assert saved.status_code == HTTPStatus.OK
    assert saved.json()["version"] == 1
    switched = await browser.client.put(
        path,
        json={"mode": "messages_and_requests", "expected_version": 1},
        headers=await write_headers(browser.client),
    )
    assert switched.status_code == HTTPStatus.OK
    assert (await browser.client.put(path, json=body, headers=headers)).json() == saved.json()
    assert (await browser.client.get(path)).json() == switched.json()
    stale = await browser.client.put(path, json=body, headers=await write_headers(browser.client))
    assert stale.status_code == HTTPStatus.CONFLICT
    assert "push" not in saved.text
    assert "permission" not in saved.text
