from http import HTTPStatus
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.media.processing import ImageFailure, InvalidImageError
from studymate.application.profiles.goals import CompleteGoalCommand, CompleteOwnGoal
from studymate.application.profiles.help_subjects import SaveHelpCommand, SaveOwnHelpSubjects
from studymate.domain.media import MediaObjectRef
from studymate.domain.study_context import HelpSubject, HelpSubjects
from studymate.infrastructure.persistence.discovery_profiles import SqlDiscoveryProfileTransaction
from studymate.infrastructure.persistence.goals import SqlGoalUnitOfWork
from studymate.infrastructure.persistence.help_subjects import SqlHelpUnitOfWork
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
)
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.report_models import (
    ProfileAccessRecord,
    ProfileReportRecord,
)
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.people_models import (
    BlockStateResponse,
    OwnBlocksResponse,
    ProfileReportReceipt,
    PublicProfileResponse,
)
from tests.image_fixture import encoded
from tests.integration.catalogue_fixture import subject
from tests.integration.http_identity import BrowserHarness, write_headers
from tests.integration.media_fixture import Storage
from tests.integration.people_fixture import mounted

pytestmark = pytest.mark.integration
PRIVATE = "Private incident narrative must remain only in retained business storage"


async def test_actual_public_profile_and_current_photo_are_authorised_and_private(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    api = await mounted(browser, identity_engine)
    response = await browser.client.get(f"/api/v1/people/{api.peer.id}")
    assert response.status_code == HTTPStatus.OK
    assert response.headers["cache-control"] == "no-store"
    profile = PublicProfileResponse.model_validate(response.json())
    assert profile.id == api.peer.id
    assert profile.goal is not None
    assert not profile.own_block.blocked
    assert profile.own_block.version == 0
    assert "mail.apu.edu.my" not in response.text
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions() as session:
        context = await session.get(ProfileAccessRecord, profile.access_context_id)
        assert context is not None
        assert context.viewer_id == api.viewer.id
        assert context.target_id == api.peer.id
        assert context.request_id == UUID(response.headers["x-request-id"])
        reference = await SqlDiscoveryProfileTransaction(session, api.peer.id).display_reference(
            api.peer.id, profile.photo.version
        )
    assert reference is not None
    assert str(reference.upload_id) not in response.text
    data = encoded(format_name="JPEG")
    browser.storage.retained[reference] = data
    photo = await browser.client.get(profile.photo.display_url)
    assert photo.status_code == HTTPStatus.OK
    assert photo.headers["content-type"] == "image/jpeg"
    assert photo.headers["x-content-type-options"] == "nosniff"
    assert "no-store" in photo.headers["cache-control"]
    assert photo.content == data
    browser.storage.retained.clear()
    unavailable = await browser.client.get(profile.photo.display_url)
    assert unavailable.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert unavailable.json()["code"] == "media_storage_unavailable"
    assert (await browser.client.get(f"/api/v1/people/{api.peer.id}")).status_code == HTTPStatus.OK


async def test_block_report_unblock_and_old_replay_keep_current_state_truthful(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    api = await mounted(browser, identity_engine)
    client = browser.client
    profile = PublicProfileResponse.model_validate(
        (await client.get(f"/api/v1/people/{api.peer.id}")).json()
    )
    peer_cookie = {"Cookie": f"{SESSION_COOKIE}={api.peer.credential.value}"}
    reverse = await client.get(f"/api/v1/people/{api.viewer.id}", headers=peer_cookie)
    assert reverse.status_code == HTTPStatus.OK
    headers = await write_headers(client)
    body = {
        "blocked": True,
        "expected_version": profile.own_block.version,
        "context_id": str(profile.access_context_id),
    }
    path = f"/api/v1/me/blocks/{api.peer.id}"
    initial = await client.put(path, json=body, headers=headers)
    assert initial.status_code == HTTPStatus.OK
    state = BlockStateResponse.model_validate(initial.json())
    assert state.blocked
    assert state.version == 1
    changed = await client.put(path, json={**body, "blocked": False}, headers=headers)
    assert changed.status_code == HTTPStatus.CONFLICT
    assert changed.json()["code"] == "idempotency_conflict"
    assert (await client.get(f"/api/v1/people/{api.peer.id}")).status_code == HTTPStatus.NOT_FOUND
    other = await client.get(
        f"/api/v1/people/{api.viewer.id}",
        headers=peer_cookie,
    )
    assert other.status_code == HTTPStatus.NOT_FOUND
    blocked = OwnBlocksResponse.model_validate((await client.get("/api/v1/me/blocks")).json())
    assert len(blocked.people) == 1
    assert blocked.people[0].block == state
    report = await client.post(
        "/api/v1/reports",
        json={
            "kind": "profile",
            "context_id": str(profile.access_context_id),
            "category": "other",
            "comment": PRIVATE,
        },
        headers=await write_headers(client),
    )
    assert report.status_code == HTTPStatus.CREATED
    assert PRIVATE not in report.text
    removed = await client.put(
        path,
        json={"blocked": False, "expected_version": state.version},
        headers=await write_headers(client),
    )
    assert removed.status_code == HTTPStatus.OK
    current = BlockStateResponse.model_validate(removed.json())
    assert not current.blocked
    assert (await client.put(path, json=body, headers=headers)).json() == initial.json()
    latest = PublicProfileResponse.model_validate(
        (await client.get(f"/api/v1/people/{api.peer.id}")).json()
    )
    assert latest.own_block == current
    assert not OwnBlocksResponse.model_validate(
        (await client.get("/api/v1/me/blocks")).json()
    ).people


async def test_report_receipt_replay_is_private_and_has_one_canonical_origin(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    api = await mounted(browser, identity_engine)
    client = browser.client
    profile = PublicProfileResponse.model_validate(
        (await client.get(f"/api/v1/people/{api.peer.id}")).json()
    )
    headers = {**await write_headers(client), "X-Action-ID": str(uuid4())}
    body = {
        "kind": "profile",
        "context_id": str(profile.access_context_id),
        "category": "other",
        "comment": PRIVATE,
    }
    response = await client.post("/api/v1/reports", json=body, headers=headers)
    assert response.status_code == HTTPStatus.CREATED
    receipt = ProfileReportReceipt.model_validate(response.json())
    assert receipt.context_id == profile.access_context_id
    assert PRIVATE not in response.text
    assert (
        await client.post("/api/v1/reports", json=body, headers=headers)
    ).json() == response.json()
    conflict = await client.post(
        "/api/v1/reports", json={**body, "comment": "Edited private narrative"}, headers=headers
    )
    assert conflict.status_code == HTTPStatus.CONFLICT
    async with async_sessionmaker(identity_engine)() as session:
        report = await session.get(ProfileReportRecord, receipt.id)
        assert report is not None
        assert report.comment == PRIVATE
        event = (
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "report.created")
            )
        ).one()
        assert event.report_id == receipt.id
        assert event.request_id == UUID(response.headers["x-request-id"])
        assert event.action_id == UUID(headers["X-Action-ID"])


async def test_profile_report_rejects_foreign_context_and_invalid_explanation(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    api = await mounted(browser, identity_engine)
    foreign = await api.services.profile(api.peer.credential, api.viewer.id)
    body = {"kind": "profile", "context_id": str(foreign.access_context.id), "category": "spam"}
    missing = await browser.client.post(
        "/api/v1/reports", json=body, headers=await write_headers(browser.client)
    )
    assert missing.status_code == HTTPStatus.NOT_FOUND
    assert missing.json()["code"] == "report_context_unavailable"
    malformed = await browser.client.post(
        "/api/v1/reports",
        json={**body, "category": "other", "comment": "   "},
        headers=await write_headers(browser.client),
    )
    assert malformed.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    injected = await browser.client.post(
        "/api/v1/reports",
        json={**body, "actor_id": str(api.peer.id)},
        headers=await write_headers(browser.client),
    )
    assert injected.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    async with async_sessionmaker(identity_engine)() as session:
        assert await session.scalar(select(func.count()).select_from(ProfileReportRecord)) == 0


async def test_report_quota_has_safe_retry_without_dropping_retained_reports(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    api = await mounted(browser, identity_engine)
    profile = await api.services.profile(api.viewer.credential, api.peer.id)
    body = {"kind": "profile", "context_id": str(profile.access_context.id), "category": "spam"}
    for _ in range(api.services.report.policy.maximum_recent):
        response = await browser.client.post(
            "/api/v1/reports", json=body, headers=await write_headers(browser.client)
        )
        assert response.status_code == HTTPStatus.CREATED
    limited = await browser.client.post(
        "/api/v1/reports", json=body, headers=await write_headers(browser.client)
    )
    assert limited.status_code == HTTPStatus.TOO_MANY_REQUESTS
    assert limited.json()["code"] == "report_rate_limited"
    assert int(limited.headers["retry-after"]) > 0


@pytest.mark.parametrize("guard", ["origin", "csrf"])
async def test_people_writes_enforce_existing_browser_authority(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
    guard: str,
) -> None:
    api = await mounted(browser, identity_engine)
    profile = await api.services.profile(api.viewer.credential, api.peer.id)
    headers = await write_headers(browser.client)
    if guard == "origin":
        headers["Origin"] = "https://foreign.example.test"
    else:
        headers["X-CSRF-Token"] = "invalid"
    response = await browser.client.put(
        f"/api/v1/me/blocks/{api.peer.id}",
        json={
            "blocked": True,
            "expected_version": 0,
            "context_id": str(profile.access_context.id),
        },
        headers=headers,
    )
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert response.headers["x-request-id"] == response.json()["request_id"]
    assert not OwnBlocksResponse.model_validate(
        (await browser.client.get("/api/v1/me/blocks")).json()
    ).people


async def test_report_body_bound_and_block_cursor_errors_remain_sanitised(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    await mounted(browser, identity_engine)
    response = await browser.client.post(
        "/api/v1/reports",
        content=b"x" * 8193,
        headers={**await write_headers(browser.client), "Content-Type": "application/json"},
    )
    assert response.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert response.json()["code"] == "command_body_rejected"
    assert "x" * 100 not in response.text
    invalid = await browser.client.get("/api/v1/me/blocks", params={"cursor": "!"})
    assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert invalid.json()["code"] == "invalid_cursor"


async def test_deleted_peer_is_neutral_publicly_but_own_unblock_stays_available(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    api = await mounted(browser, identity_engine)
    profile = await api.services.profile(api.viewer.credential, api.peer.id)
    path = f"/api/v1/me/blocks/{api.peer.id}"
    blocked = await browser.client.put(
        path,
        json={"blocked": True, "expected_version": 0, "context_id": str(profile.access_context.id)},
        headers=await write_headers(browser.client),
    )
    state = BlockStateResponse.model_validate(blocked.json())
    async with async_sessionmaker(identity_engine).begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == api.peer.id)
            .values(deleted_at=func.clock_timestamp())
        )
    assert (
        await browser.client.get(f"/api/v1/people/{api.peer.id}")
    ).status_code == HTTPStatus.NOT_FOUND
    listed = OwnBlocksResponse.model_validate(
        (await browser.client.get("/api/v1/me/blocks")).json()
    )
    assert listed.people[0].deleted
    assert listed.people[0].display_name is None
    removed = await browser.client.put(
        path,
        json={"blocked": False, "expected_version": state.version},
        headers=await write_headers(browser.client),
    )
    assert removed.status_code == HTTPStatus.OK
    assert not BlockStateResponse.model_validate(removed.json()).blocked


async def test_public_helper_context_survives_goal_completion_without_account_roles(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    api = await mounted(browser, identity_engine)
    original = await api.services.profile(api.viewer.credential, api.peer.id)
    assert original.goal is not None
    course = await subject(identity_engine, name="Synthetic declared help subject")
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    hasher = Sha256SessionHasher()
    fingerprinter = HmacIntentFingerprinter(bytes(range(32)))
    await SaveOwnHelpSubjects(SqlHelpUnitOfWork(sessions), hasher, fingerprinter)(
        SaveHelpCommand(
            api.peer.credential, HelpSubjects((HelpSubject(course.id),)), 0, IntentKey(str(uuid4()))
        )
    )
    await CompleteOwnGoal(SqlGoalUnitOfWork(sessions), hasher, fingerprinter)(
        CompleteGoalCommand(
            api.peer.credential,
            original.goal.goal.id,
            original.goal.goal.version,
            IntentKey(str(uuid4())),
        )
    )
    response = await browser.client.get(f"/api/v1/people/{api.peer.id}")
    assert response.status_code == HTTPStatus.OK
    value = PublicProfileResponse.model_validate(response.json())
    assert value.goal is None
    assert value.help_subjects is not None
    assert value.help_subjects.subjects[0].subject_id == course.id
    assert value.help_subjects.subjects[0].label == course.name
    assert "task" not in response.json()
    async with sessions() as session:
        context = await session.get(ProfileAccessRecord, value.access_context_id)
        assert context is not None
        assert context.goal_id is None
        assert context.help_version == value.help_subjects.version


@pytest.mark.parametrize("state", ["unverified", "banned", "deleted"])
async def test_all_people_endpoints_recheck_live_student_authority(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
    state: str,
) -> None:
    api = await mounted(browser, identity_engine)
    profile = await api.services.profile(api.viewer.credential, api.peer.id)
    headers = await write_headers(browser.client)
    async with async_sessionmaker(identity_engine).begin() as session:
        if state == "unverified":
            await session.execute(
                update(InstitutionalBindingRecord)
                .where(InstitutionalBindingRecord.account_id == api.viewer.id)
                .values(revoked_at=func.clock_timestamp())
            )
        else:
            column = AccountRecord.banned_at if state == "banned" else AccountRecord.deleted_at
            await session.execute(
                update(AccountRecord)
                .where(AccountRecord.id == api.viewer.id)
                .values({column: func.clock_timestamp()})
            )
    responses = [
        await browser.client.get(f"/api/v1/people/{api.peer.id}"),
        await browser.client.get(f"/api/v1/people/{api.peer.id}/photo/1"),
        await browser.client.get("/api/v1/me/blocks"),
        await browser.client.put(
            f"/api/v1/me/blocks/{api.peer.id}",
            json={
                "blocked": True,
                "expected_version": 0,
                "context_id": str(profile.access_context.id),
            },
            headers=headers,
        ),
        await browser.client.post(
            "/api/v1/reports",
            json={
                "kind": "profile",
                "context_id": str(profile.access_context.id),
                "category": "spam",
            },
            headers=headers,
        ),
    ]
    expected = HTTPStatus.UNAUTHORIZED if state == "deleted" else HTTPStatus.FORBIDDEN
    assert all(response.status_code == expected for response in responses)
    assert all(response.headers["cache-control"] == "no-store" for response in responses)


async def test_corrupt_retained_photo_is_storage_failure_not_profile_ineligibility(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = await mounted(browser, identity_engine)
    response = await browser.client.get(f"/api/v1/people/{api.peer.id}")
    profile = PublicProfileResponse.model_validate(response.json())

    async def invalid_display(_storage: Storage, _reference: MediaObjectRef) -> bytes:
        raise InvalidImageError(ImageFailure.TOO_LARGE)

    monkeypatch.setattr(Storage, "read", invalid_display)
    photo = await browser.client.get(profile.photo.display_url)
    assert photo.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert photo.json()["code"] == "media_storage_unavailable"
    assert (await browser.client.get(f"/api/v1/people/{api.peer.id}")).status_code == HTTPStatus.OK
