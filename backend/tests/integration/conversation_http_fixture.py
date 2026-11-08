from dataclasses import dataclass
from http import HTTPStatus
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.presentation.browser import SESSION_COOKIE
from tests.integration.http_identity import BrowserHarness, write_headers
from tests.integration.people_fixture import PeopleHarness
from tests.integration.test_discovery_http import mounted


@dataclass(frozen=True, slots=True)
class ConversationHarness:
    actors: PeopleHarness
    conversation_id: UUID

    @property
    def prefix(self) -> str:
        return f"/api/v1/conversations/{self.conversation_id}"


async def accepted_conversation(
    browser: BrowserHarness, engine: AsyncEngine
) -> ConversationHarness:
    actors = await mounted(browser, engine)
    preview = await browser.client.post(
        "/api/v1/requests/preview",
        json={"person_id": str(actors.peer.id), "mode": "find_help"},
        headers=await write_headers(browser.client),
    )
    assert preview.status_code == HTTPStatus.OK
    sent = await browser.client.post(
        "/api/v1/requests",
        json={
            "person_id": str(actors.peer.id),
            "preview_id": preview.json()["preview_id"],
            "text": "Explicit reviewed conversation context",
        },
        headers=await write_headers(browser.client),
    )
    assert sent.status_code == HTTPStatus.OK
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, actors.peer.credential.value)
    accepted = await browser.client.post(
        f"/api/v1/requests/{sent.json()['request_id']}/accept",
        json={"person_id": str(actors.viewer.id), "expected_version": sent.json()["version"]},
        headers=await write_headers(browser.client),
    )
    assert accepted.status_code == HTTPStatus.OK
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, actors.viewer.credential.value)
    return ConversationHarness(actors, UUID(accepted.json()["conversation_id"]))
