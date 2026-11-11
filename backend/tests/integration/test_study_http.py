from http import HTTPStatus
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.presentation.catalogue import SubjectsResponse
from studymate.presentation.study_models import (
    GoalResponse,
    HelpResponse,
    OwnGoalResponse,
    OwnHelpResponse,
)
from tests.integration.catalogue_fixture import subject
from tests.integration.http_identity import BrowserHarness, verified, write_headers

pytestmark = pytest.mark.integration


def goal_payload() -> dict[str, object]:
    return {"subject": {"kind": "custom", "label": "  Synthetic   subject "}, "expected_version": 0}


async def test_goal_http_history_completion_and_old_target_cannot_complete_replacement(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    await verified(browser, identity_engine)
    client = browser.client
    assert OwnGoalResponse.model_validate((await client.get("/api/v1/me/goal")).json()).goal is None
    headers = await write_headers(client)
    first_response = await client.put("/api/v1/me/goal", json=goal_payload(), headers=headers)
    assert first_response.status_code == HTTPStatus.OK
    first = GoalResponse.model_validate(first_response.json())
    assert first.subject.kind == "custom"
    assert not first.shared_learning
    edited = await client.put(
        "/api/v1/me/goal",
        json={
            **goal_payload(),
            "expected_goal_id": str(first.id),
            "expected_version": first.version,
            "topic": "Private topic",
            "context": " Private context ",
        },
        headers=await write_headers(client),
    )
    second = GoalResponse.model_validate(edited.json())
    assert second.id == first.id
    assert second.version == first.version + 1
    assert (
        await client.put("/api/v1/me/goal", json=goal_payload(), headers=headers)
    ).json() == first_response.json()
    completion_headers = await write_headers(client)
    completion_body = {"goal_id": str(second.id), "expected_version": second.version}
    completed = await client.post(
        "/api/v1/me/goal/complete", json=completion_body, headers=completion_headers
    )
    assert GoalResponse.model_validate(completed.json()).completed_at is not None
    assert OwnGoalResponse.model_validate((await client.get("/api/v1/me/goal")).json()).goal is None
    replacement = GoalResponse.model_validate(
        (
            await client.put(
                "/api/v1/me/goal", json=goal_payload(), headers=await write_headers(client)
            )
        ).json()
    )
    stale = await client.post(
        "/api/v1/me/goal/complete", json=completion_body, headers=await write_headers(client)
    )
    assert stale.status_code == HTTPStatus.CONFLICT
    assert stale.json()["recovery"]["current_goal_id"] == str(replacement.id)
    assert (
        await client.post(
            "/api/v1/me/goal/complete", json=completion_body, headers=completion_headers
        )
    ).json() == completed.json()


async def test_help_http_saved_clear_and_original_retry_preserve_labels(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    await verified(browser, identity_engine)
    known = await subject(identity_engine)
    client = browser.client
    assert (
        OwnHelpResponse.model_validate(
            (await client.get("/api/v1/me/help-subjects")).json()
        ).selection
        is None
    )
    headers = await write_headers(client)
    body = {
        "subjects": [{"subject_id": str(known.id), "topic_note": " Private topic "}],
        "expected_version": 0,
    }
    first = await client.put("/api/v1/me/help-subjects", json=body, headers=headers)
    selection = HelpResponse.model_validate(first.json())
    assert selection.subjects[0].label == known.name
    assert selection.subjects[0].topic_note == "Private topic"
    duplicate = await client.put(
        "/api/v1/me/help-subjects",
        json={**body, "subjects": [{"subject_id": str(known.id)}, {"subject_id": str(known.id)}]},
        headers=await write_headers(client),
    )
    assert duplicate.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    clear = await client.put(
        "/api/v1/me/help-subjects",
        json={"subjects": [], "expected_version": selection.version},
        headers=await write_headers(client),
    )
    cleared = HelpResponse.model_validate(clear.json())
    assert cleared.subjects == ()
    assert (
        await client.put("/api/v1/me/help-subjects", json=body, headers=headers)
    ).json() == first.json()
    stale = await client.put(
        "/api/v1/me/help-subjects", json=body, headers=await write_headers(client)
    )
    assert stale.json()["code"] == "help_version_conflict"
    unavailable = await client.put(
        "/api/v1/me/help-subjects",
        json={"subjects": [{"subject_id": str(uuid4())}], "expected_version": cleared.version},
        headers=await write_headers(client),
    )
    assert unavailable.json()["code"] == "subject_unavailable"
    assert unavailable.json()["errors"][0]["path"] == ["subjects"]


async def test_catalogue_http_is_cursor_bounded_and_never_auto_maps_custom_subject(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    await verified(browser, identity_engine)
    first = await subject(identity_engine, name="Synthetic A", aliases=("Shared alias",))
    second = await subject(identity_engine, name="Synthetic Z", aliases=("Shared alias",))
    client = browser.client
    response = await client.get("/api/v1/subjects", params={"query": "alias", "limit": 1})
    page = SubjectsResponse.model_validate(response.json())
    assert page.items[0].id == first.id
    assert page.next_cursor is not None
    final = SubjectsResponse.model_validate(
        (
            await client.get(
                "/api/v1/subjects",
                params={"query": "alias", "limit": 1, "cursor": page.next_cursor},
            )
        ).json()
    )
    assert final.items[0].id == second.id
    assert final.next_cursor is None
    invalid = await client.get("/api/v1/subjects", params={"cursor": "invalid-token"})
    assert invalid.status_code == HTTPStatus.BAD_REQUEST
    wrong_query = await client.get(
        "/api/v1/subjects", params={"query": "changed", "cursor": page.next_cursor}
    )
    assert wrong_query.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    custom = await client.put(
        "/api/v1/me/goal",
        json={**goal_payload(), "subject": {"kind": "custom", "label": first.name}},
        headers=await write_headers(client),
    )
    assert GoalResponse.model_validate(custom.json()).subject.kind == "custom"
