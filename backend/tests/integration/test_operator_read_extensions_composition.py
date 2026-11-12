from datetime import datetime, timedelta
from http import HTTPStatus
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.persistence.registration_models import PolicyDocumentRecord
from studymate.presentation.browser import SESSION_COOKIE
from tests.integration.http_identity import BrowserHarness
from tests.integration.operator.test_reads import operator
from tests.integration.student_actor import actor
from tests.integration.test_message_commands import chat

pytestmark = pytest.mark.integration


async def test_root_public_policy_history_is_metadata_only_without_session_or_future_versions(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        at = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(at, datetime)
        for number, kind, date in (
            (1, "terms", at - timedelta(days=2)),
            (2, "terms", at - timedelta(days=1)),
            (3, "privacy", at - timedelta(days=1)),
            (4, "terms", at + timedelta(days=1)),
        ):
            session.add(
                PolicyDocumentRecord(
                    id=uuid4(),
                    kind=kind,
                    version=f"public-history-{number}",
                    title=f"Title {number}",
                    content="PRIVATE_DOCUMENT_BODY_CANARY",
                    published_at=date,
                )
            )
    first = await browser.client.get("/api/v1/policies/terms/versions", params={"limit": 1})
    assert first.status_code == HTTPStatus.OK
    assert [item["reference"]["version"] for item in first.json()["items"]] == ["public-history-2"]
    assert "PRIVATE_DOCUMENT_BODY_CANARY" not in first.text
    second = await browser.client.get(
        "/api/v1/policies/terms/versions",
        params={
            "limit": 1,
            "cursor": first.json()["next_cursor"],
        },
    )
    assert second.status_code == HTTPStatus.OK
    assert [item["reference"]["version"] for item in second.json()["items"]] == ["public-history-1"]
    assert second.json()["next_cursor"] is None
    detail = await browser.client.get(
        "/api/v1/policies/terms", params={"version": "public-history-1"}
    )
    assert detail.status_code == HTTPStatus.OK
    assert detail.json()["content"] == "PRIVATE_DOCUMENT_BODY_CANARY"


async def test_root_operator_lifecycle_history_audits_empty_target_without_fake_revisions(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    viewer, target = await operator(identity_engine), await actor(identity_engine)
    browser.client.cookies.set(SESSION_COOKIE, viewer.credential.value)
    path = f"/api/v1/operator/accounts/{target.id}/lifecycle-history"
    result = await browser.client.get(path)
    assert result.status_code == HTTPStatus.OK
    assert result.headers["cache-control"] == "no-store"
    assert result.json()["revisions"] == []
    assert result.json()["anchor_version"] == 0
    sessions = async_sessionmaker(identity_engine)
    async with sessions() as session:
        audit = (await session.scalars(select(OperatorAuditRecord))).one()
        assert audit.operator_id == viewer.id
        assert audit.requested_id == target.id
        assert audit.outcome == "read"


async def test_root_message_operation_lookup_returns_actual_confirmation_and_author_scope(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    context = await chat(identity_engine)
    confirmed = await context.send()(context.command())
    assert confirmed.message is not None
    viewer = await operator(identity_engine)
    browser.client.cookies.set(SESSION_COOKIE, viewer.credential.value)
    root = f"/api/v1/operator/accounts/{context.sender.id}/message-operations"
    listing = await browser.client.get(root)
    assert listing.status_code == HTTPStatus.OK
    assert listing.headers["cache-control"] == "no-store"
    detail = await browser.client.get(root + f"/{confirmed.id}")
    assert detail.status_code == HTTPStatus.OK
    assert detail.json()["id"] == str(confirmed.id)
    assert detail.json()["message_id"] == str(confirmed.message.id)
    assert detail.json()["message"]["id"] == str(confirmed.message.id)
    foreign = await browser.client.get(
        f"/api/v1/operator/accounts/{context.recipient.id}/message-operations/{confirmed.id}"
    )
    assert foreign.status_code == HTTPStatus.NOT_FOUND
