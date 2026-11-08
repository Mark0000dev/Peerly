from http import HTTPStatus
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.presentation.browser import SESSION_COOKIE
from tests.integration.conversation_http_fixture import accepted_conversation
from tests.integration.http_identity import BrowserHarness, write_headers

pytestmark = pytest.mark.integration
EXPECTED_FEEDBACK_EVENTS = 2


async def test_actual_feedback_mount_retains_owned_outcome_and_note_without_message_publication(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    owned = await accepted_conversation(browser, identity_engine)
    outcome_path = f"{owned.prefix}/study-outcome"
    assert (await browser.client.get(outcome_path)).json() == {"outcome": None}
    headers = await write_headers(browser.client)
    body = {"answer": "yes", "expected_version": 0}
    saved = await browser.client.put(outcome_path, json=body, headers=headers)
    assert saved.status_code == HTTPStatus.OK
    assert saved.json()["version"] == 1
    assert (
        await browser.client.put(outcome_path, json=body, headers=headers)
    ).json() == saved.json()
    assert (await browser.client.get(outcome_path)).json()["outcome"] == saved.json()
    note = "PRIVATE retained feedback note"
    feedback = await browser.client.put(
        f"{owned.prefix}/feedback",
        json={"again": "yes", "team_note": note, "expected_version": 0},
        headers=await write_headers(browser.client),
    )
    assert feedback.status_code == HTTPStatus.OK
    assert feedback.json()["team_note"] == note
    own = await browser.client.get(f"{owned.prefix}/feedback")
    assert own.json()["current"] == feedback.json()
    assert own.headers["cache-control"] == "no-store"
    assert (await browser.client.get(f"{owned.prefix}/messages")).json()["messages"] == []
    summary = await browser.client.get("/api/v1/me/feedback-summary")
    assert summary.status_code == HTTPStatus.OK
    assert note not in summary.text
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, owned.actors.peer.credential.value)
    peer = await browser.client.get(f"{owned.prefix}/feedback")
    assert peer.json()["current"] is None
    assert peer.json()["outcome"] is None
    assert note not in peer.text
    async with async_sessionmaker(identity_engine)() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProductEventRecord)
                .where(ProductEventRecord.kind.in_(("study.reported", "feedback.saved")))
            )
            == EXPECTED_FEEDBACK_EVENTS
        )


async def test_actual_feedback_commands_keep_shared_body_and_privacy_guards(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    owned = await accepted_conversation(browser, identity_engine)
    for suffix in ("study-outcome", "feedback", "study-prompt-visits"):
        path = f"{owned.prefix}/{suffix}"
        method = "POST" if suffix == "study-prompt-visits" else "PUT"
        large = await browser.client.request(
            method, path, content=b"x" * 8193, headers={"Content-Type": "application/json"}
        )
        assert large.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
        assert large.json()["code"] == "command_body_rejected"
        wrong_type = await browser.client.request(
            method, path, content=b"{}", headers={"Content-Type": "text/plain"}
        )
        assert wrong_type.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    invalid = await browser.client.put(
        f"{owned.prefix}/study-outcome",
        json={"answer": "yes", "expected_version": 0, "actor_id": str(uuid4())},
        headers=await write_headers(browser.client),
    )
    assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    prompt = await browser.client.post(
        f"{owned.prefix}/study-prompt-visits", json={}, headers=await write_headers(browser.client)
    )
    assert prompt.status_code == HTTPStatus.OK
    assert prompt.json() == {"outcome": "no_offer"}


async def test_public_feedback_summary_invalid_uuid_uses_the_shared_problem_contract(
    browser: BrowserHarness,
) -> None:
    response = await browser.client.get("/api/v1/people/not-a-uuid/feedback-summary")
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.json()["code"] == "invalid_fields"
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert "detail" not in response.json()
