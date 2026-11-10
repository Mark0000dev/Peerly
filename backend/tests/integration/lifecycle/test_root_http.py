"""Actual root composition, disposable PG and controlled Google/storage boundaries only."""

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from http import HTTPStatus
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.infrastructure.lifecycle.models import LifecycleRevisionRecord
from studymate.infrastructure.lifecycle.workflow_models import AccountDeletionWorkflowRecord
from studymate.infrastructure.operator.models import (
    OperatorAccessRecord,
    OperatorAccessRevisionRecord,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.identity import IdentityResponse
from studymate.presentation.lifecycle.recovery import DELETION_STATUS_COOKIE
from tests.integration.http_identity import BrowserHarness, login, write_headers
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration
RECREATED_ACCOUNT_COUNT = 2


async def test_root_preflight_retries_delete_and_narrow_status_survive_session_clear(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    http = browser.client
    await login(http)
    identity = IdentityResponse.model_validate((await http.get("/api/v1/me")).json())
    # A second real controlled Google login creates another owned session.
    await login(http)
    headers = await write_headers(http)
    credential = http.cookies.get(SESSION_COOKIE)
    assert credential is not None
    first = await http.post("/api/v1/me/deletion-workflows", json={}, headers=headers)
    assert first.status_code == HTTPStatus.OK
    proof = http.cookies.get(DELETION_STATUS_COOKIE)
    assert proof is not None
    assert "HttpOnly" in first.headers["set-cookie"]
    assert "SameSite=strict" in first.headers["set-cookie"]
    assert "Secure" in first.headers["set-cookie"]
    assert set(first.json()) == {"workflow_id", "expires_at"}
    # A lost response and another tab using this original session repeat the
    # server-owned workflow; neither client chooses a new generation or proof.
    second, third = await asyncio.gather(
        http.post("/api/v1/me/deletion-workflows", json={}, headers=headers),
        http.post("/api/v1/me/deletion-workflows", json={}, headers=headers),
    )
    assert second.json() == first.json()
    assert third.json() == first.json()
    assert http.cookies.get(DELETION_STATUS_COOKIE) == proof
    pending = await http.get("/api/v1/me/deletion-status")
    assert pending.json()["state"] == "pending"
    body = {"workflow_id": first.json()["workflow_id"]}
    deleted = await http.post("/api/v1/me/deletion", json=body, headers=headers)
    assert deleted.status_code == HTTPStatus.OK
    assert http.cookies.get(SESSION_COOKIE) is None
    assert http.cookies.get(DELETION_STATUS_COOKIE) == proof
    status = await http.get("/api/v1/me/deletion-status")
    assert status.status_code == HTTPStatus.OK
    assert status.json()["state"] == "deleted"
    assert status.json()["workflow_id"] == body["workflow_id"]
    assert (await http.get("/api/v1/me")).status_code == HTTPStatus.UNAUTHORIZED
    # Original opaque session proof + exact original intent can recover a lost
    # command response. It grants no fresh intent or ordinary authenticated read.
    original_headers = {**headers, "Cookie": f"{SESSION_COOKIE}={credential}"}
    replay = await http.post("/api/v1/me/deletion", json=body, headers=original_headers)
    assert replay.status_code == HTTPStatus.OK
    assert replay.json() == deleted.json()
    fresh = await http.post(
        "/api/v1/me/deletion",
        json=body,
        headers={
            **original_headers,
            "Idempotency-Key": str(uuid4()),
        },
    )
    assert fresh.status_code == HTTPStatus.UNAUTHORIZED
    async with async_sessionmaker(identity_engine)() as session:
        sessions = tuple(
            await session.scalars(
                select(SessionRecord).where(SessionRecord.account_id == identity.account_id)
            )
        )
        assert len(sessions) == len(("original", "second"))
        assert all(stored.revoked_at is not None for stored in sessions)
        assert (
            await session.scalar(select(func.count()).select_from(AccountDeletionWorkflowRecord))
            == 1
        )
        assert await session.scalar(select(func.count()).select_from(LifecycleRevisionRecord)) == 1
    http.cookies.clear()
    no_proof = await http.get("/api/v1/me/deletion-status", params=body)
    assert no_proof.status_code == HTTPStatus.NOT_FOUND


async def test_root_deleted_google_identity_creates_distinct_unverified_account(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    http = browser.client
    await login(http)
    headers = await write_headers(http)
    prepared = await http.post("/api/v1/me/deletion-workflows", json={}, headers=headers)
    assert prepared.status_code == HTTPStatus.OK
    deleted = await http.post(
        "/api/v1/me/deletion",
        json={
            "workflow_id": prepared.json()["workflow_id"],
        },
        headers=headers,
    )
    assert deleted.status_code == HTTPStatus.OK
    started = await http.get("/api/v1/auth/google/start")
    state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]
    await http.get("/api/v1/auth/google/callback", params={"state": state, "code": "code"})
    fresh = IdentityResponse.model_validate((await http.get("/api/v1/me")).json())
    assert fresh.membership_status == "unverified"
    assert fresh.registration is None
    async with async_sessionmaker(identity_engine)() as session:
        accounts = tuple(await session.scalars(select(AccountRecord)))
        assert len(accounts) == RECREATED_ACCOUNT_COUNT
        assert any(account.deleted_at is not None for account in accounts)
        assert (
            next(account for account in accounts if account.id == fresh.account_id).deleted_at
            is None
        )


async def grant(browser: BrowserHarness, engine: AsyncEngine) -> UUID:
    identity = IdentityResponse.model_validate((await browser.client.get("/api/v1/me")).json())
    async with async_sessionmaker(engine).begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        session.add(OperatorAccessRecord(account_id=identity.account_id, current_version=1))
        await session.flush()
        session.add(
            OperatorAccessRevisionRecord(
                account_id=identity.account_id,
                version=1,
                active=True,
                changed_at=now,
            )
        )
    return identity.account_id


async def test_root_ban_requires_actual_grant_and_keeps_private_reason_out_of_receipts(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    http = browser.client
    await login(http)
    headers = await write_headers(http)
    target = await actor(identity_engine)
    path = f"/api/v1/operator/accounts/{target.id}/ban"
    body = {"banned": True, "reason": "PRIVATE_ROOT_MODERATION_REASON"}
    assert (await http.put(path, json=body, headers=headers)).status_code == HTTPStatus.FORBIDDEN
    owner = await grant(browser, identity_engine)
    first = await http.put(path, json=body, headers=headers)
    assert first.status_code == HTTPStatus.OK
    assert first.json()["changed"] is True
    assert "PRIVATE_ROOT_MODERATION_REASON" not in first.text
    assert (await http.put(path, json=body, headers=headers)).json() == first.json()
    noop = await http.put(path, json=body, headers={**headers, "Idempotency-Key": str(uuid4())})
    assert noop.status_code == HTTPStatus.OK
    assert noop.json()["changed"] is False
    unban = await http.put(
        path,
        json={**body, "banned": False},
        headers={
            **headers,
            "Idempotency-Key": str(uuid4()),
        },
    )
    assert unban.status_code == HTTPStatus.OK
    assert unban.json()["account"]["banned_at"] is None
    async with async_sessionmaker(identity_engine)() as session:
        events = tuple(
            await session.scalars(
                select(ProductEventRecord).where(
                    ProductEventRecord.kind == "account.lifecycle_changed"
                )
            )
        )
        assert len(events) == len(("ban", "unban"))
        assert all(event.account_id == owner for event in events)
        assert all(event.lifecycle_account_id == target.id for event in events)
        assert all(event.lifecycle_operation in {"ban", "unban"} for event in events)


@pytest.mark.parametrize(
    ("path", "method"),
    [
        ("/api/v1/me/deletion", "POST"),
        ("/api/v1/me/deletion-workflows", "POST"),
        (f"/api/v1/operator/accounts/{UUID(int=1)}/ban", "PUT"),
    ],
)
async def test_actual_root_lifecycle_body_admission(
    browser: BrowserHarness,
    path: str,
    method: str,
) -> None:
    unsupported = await browser.client.request(
        method,
        path,
        content="{}",
        headers={
            "Content-Type": "text/plain",
        },
    )
    assert unsupported.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    oversized = await browser.client.request(
        method,
        path,
        content=b"x" * 8193,
        headers={
            "Content-Type": "application/json",
        },
    )
    assert oversized.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE

    async def slow() -> AsyncIterator[bytes]:
        yield b"{"
        await asyncio.Event().wait()

    timeout = await browser.client.request(
        method,
        path,
        content=slow(),
        headers={
            "Content-Type": "application/json",
        },
    )
    assert timeout.status_code == HTTPStatus.REQUEST_TIMEOUT
    assert timeout.json()["code"] == "command_body_rejected"
