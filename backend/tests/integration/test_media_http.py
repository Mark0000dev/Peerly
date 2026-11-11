import hashlib
from datetime import UTC, datetime
from http import HTTPStatus
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.media.uploads import MAX_PENDING_UPLOADS
from studymate.domain.media import PhotoUploadState
from studymate.infrastructure.media.images import BoundedImageProcessor
from studymate.infrastructure.persistence.identity_models import InstitutionalBindingRecord
from studymate.presentation.command_body_limit import COMMAND_BODY_BYTES
from studymate.presentation.identity import IdentityResponse
from studymate.presentation.media import (
    PhotoUploadResponse,
    StartPhotoRequest,
    UploadAccessResponse,
)
from tests.image_fixture import encoded
from tests.integration.http_identity import BrowserHarness, login, verified, write_headers
from tests.integration.media_fixture import worker

pytestmark = pytest.mark.integration


def payload(data: bytes) -> dict[str, object]:
    return StartPhotoRequest(
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        content_type="image/png",
        expected_photo_version=0,
    ).model_dump(mode="json")


async def test_media_http_complete_owned_pipeline_and_postpublication_cancel(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    await verified(browser, identity_engine)
    client, data = browser.client, encoded()
    headers = await write_headers(client)
    started = await client.post("/api/v1/media/uploads", json=payload(data), headers=headers)
    assert started.status_code == HTTPStatus.ACCEPTED
    upload = PhotoUploadResponse.model_validate(started.json())
    assert upload.state == PhotoUploadState.UPLOADING
    assert "sha256" not in started.text
    assert started.headers["cache-control"] == "no-store"
    repeated = await client.post("/api/v1/media/uploads", json=payload(data), headers=headers)
    assert repeated.json() == started.json()
    access = await client.post(
        f"/api/v1/media/uploads/{upload.id}/access", headers=await write_headers(client)
    )
    assert access.status_code == HTTPStatus.OK
    assert UploadAccessResponse.model_validate(access.json()).fields
    assert access.headers["referrer-policy"] == "no-referrer"
    browser.storage.data = data
    final_headers = await write_headers(client)
    final = await client.post(f"/api/v1/media/uploads/{upload.id}/finalize", headers=final_headers)
    assert final.status_code == HTTPStatus.ACCEPTED
    assert PhotoUploadResponse.model_validate(final.json()).state == PhotoUploadState.QUEUED
    processor = BoundedImageProcessor()
    try:
        await worker(identity_engine, browser.storage, processor)()
    finally:
        await processor.close()
    ready = PhotoUploadResponse.model_validate(
        (await client.get(f"/api/v1/media/{upload.id}")).json()
    )
    assert ready.state == PhotoUploadState.READY
    assert ready.display_url is not None
    displayed = await client.get(ready.display_url)
    assert displayed.status_code == HTTPStatus.OK
    assert displayed.headers["content-type"] == "image/jpeg"
    assert displayed.headers["x-content-type-options"] == "nosniff"
    assert displayed.headers["cache-control"] == "private, no-store"
    assert displayed.content.startswith(b"\xff\xd8\xff")
    assert (
        await client.post(f"/api/v1/media/uploads/{upload.id}/finalize", headers=final_headers)
    ).json() == final.json()
    cancelled = await client.post(
        f"/api/v1/media/uploads/{upload.id}/cancel", headers=await write_headers(client)
    )
    assert PhotoUploadResponse.model_validate(cancelled.json()).state == PhotoUploadState.READY
    unavailable = await client.post(
        f"/api/v1/media/uploads/{upload.id}/access", headers=await write_headers(client)
    )
    assert unavailable.status_code == HTTPStatus.CONFLICT
    assert unavailable.json()["code"] == "upload_not_uploading"
    assert not IdentityResponse.model_validate(
        (await client.get("/api/v1/me")).json()
    ).capabilities.can_use_student_features


async def test_media_guards_membership_csrf_origin_and_strict_payload(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    client, data = browser.client, encoded()
    assert (await client.get(f"/api/v1/media/{uuid4()}")).status_code == HTTPStatus.UNAUTHORIZED
    await login(client)
    unverified = await client.post(
        "/api/v1/media/uploads", json=payload(data), headers=await write_headers(client)
    )
    assert unverified.status_code == HTTPStatus.FORBIDDEN
    identity = IdentityResponse.model_validate((await client.get("/api/v1/me")).json())
    async with async_sessionmaker(identity_engine).begin() as session:
        session.add(
            InstitutionalBindingRecord(
                account_id=identity.account_id,
                email="synthetic-http@mail.apu.edu.my",
                verified_at=datetime.now(UTC),
            )
        )
    headers = await write_headers(client)
    denied = await client.post(
        "/api/v1/media/uploads",
        json=payload(data),
        headers={**headers, "Origin": "https://foreign.test"},
    )
    assert denied.json()["code"] == "origin_denied"
    denied = await client.post(
        "/api/v1/media/uploads", json=payload(data), headers={**headers, "X-CSRF-Token": "wrong"}
    )
    assert denied.json()["code"] == "csrf_denied"
    invalid = await client.post(
        "/api/v1/media/uploads",
        json={**payload(data), "size_bytes": True, "private": "never echo me"},
        headers=headers,
    )
    assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "never echo me" not in invalid.text
    assert (await client.get(f"/api/v1/media/{uuid4()}")).status_code == HTTPStatus.NOT_FOUND


async def test_media_storage_failure_is_safe_without_fake_grant(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    await verified(browser, identity_engine)
    client = browser.client
    started = await client.post(
        "/api/v1/media/uploads", json=payload(encoded()), headers=await write_headers(client)
    )
    upload = PhotoUploadResponse.model_validate(started.json())
    browser.storage.unavailable = True
    response = await client.post(
        f"/api/v1/media/uploads/{upload.id}/access", headers=await write_headers(client)
    )
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json()["code"] == "media_storage_unavailable"
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert "policy" not in response.text


async def test_media_command_size_and_empty_action_body_are_bounded(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    await verified(browser, identity_engine)
    client = browser.client
    headers = await write_headers(client)
    oversized = await client.post(
        "/api/v1/media/uploads",
        content=b"x" * (COMMAND_BODY_BYTES + 1),
        headers={**headers, "Content-Type": "application/json"},
    )
    assert oversized.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    unsupported = await client.post("/api/v1/media/uploads", content=b"binary", headers=headers)
    assert unsupported.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    ignored = await client.post(
        f"/api/v1/media/uploads/{uuid4()}/cancel", json={"unexpected": "private"}, headers=headers
    )
    assert ignored.status_code == HTTPStatus.BAD_REQUEST
    assert "private" not in ignored.text


async def test_media_intent_conflict_and_admission_limit_are_explicit(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    await verified(browser, identity_engine)
    client, data = browser.client, encoded()
    headers = await write_headers(client)
    first = await client.post("/api/v1/media/uploads", json=payload(data), headers=headers)
    upload = PhotoUploadResponse.model_validate(first.json())
    changed = await client.post(
        "/api/v1/media/uploads",
        json={**payload(data), "size_bytes": len(data) + 1},
        headers=headers,
    )
    assert changed.status_code == HTTPStatus.CONFLICT
    assert changed.json()["code"] == "idempotency_conflict"
    for _ in range(MAX_PENDING_UPLOADS - 1):
        assert (
            await client.post(
                "/api/v1/media/uploads", json=payload(data), headers=await write_headers(client)
            )
        ).status_code == HTTPStatus.ACCEPTED
    limited = await client.post(
        "/api/v1/media/uploads", json=payload(data), headers=await write_headers(client)
    )
    assert limited.status_code == HTTPStatus.TOO_MANY_REQUESTS
    assert limited.json()["code"] == "photo_upload_rate_limited"
    assert int(limited.headers["retry-after"]) > 0
    cancelled = await client.post(
        f"/api/v1/media/uploads/{upload.id}/cancel", headers=await write_headers(client)
    )
    assert PhotoUploadResponse.model_validate(cancelled.json()).state == PhotoUploadState.CANCELLED
    invalid_version = await client.post(
        "/api/v1/media/uploads",
        json={**payload(data), "expected_photo_version": 1},
        headers=await write_headers(client),
    )
    assert invalid_version.status_code == HTTPStatus.CONFLICT
    assert invalid_version.json()["code"] == "photo_version_conflict"
    assert invalid_version.json()["recovery"]["current_version"] == 0


async def test_media_unready_display_unknown_action_and_missing_cookie_are_safe(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    await verified(browser, identity_engine)
    client = browser.client
    upload = PhotoUploadResponse.model_validate(
        (
            await client.post(
                "/api/v1/media/uploads",
                json=payload(encoded()),
                headers=await write_headers(client),
            )
        ).json()
    )
    assert (
        await client.get(f"/api/v1/media/{upload.id}/display")
    ).status_code == HTTPStatus.NOT_FOUND
    unknown = await client.post(
        f"/api/v1/media/uploads/{uuid4()}/finalize", headers=await write_headers(client)
    )
    assert unknown.status_code == HTTPStatus.NOT_FOUND
    client.cookies.clear()
    assert (
        await client.get(f"/api/v1/media/{upload.id}/display")
    ).status_code == HTTPStatus.UNAUTHORIZED
    unauthenticated = await client.post(
        f"/api/v1/media/uploads/{upload.id}/cancel", headers={"Idempotency-Key": str(uuid4())}
    )
    assert unauthenticated.status_code == HTTPStatus.UNAUTHORIZED
