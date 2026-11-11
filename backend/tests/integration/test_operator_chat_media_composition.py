"""Actual root retained chat object source, canonical audit and typed inspection metadata."""

from dataclasses import replace
from http import HTTPStatus
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.domain.operator.chat_media import OperatorChatMediaKind
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.presentation.browser import SESSION_COOKIE
from tests.integration.http_identity import BrowserHarness
from tests.integration.migrations import run_revision_step
from tests.integration.operator.chat_media_read_test import PRIVATE_CHAT_BYTES, chat_media

pytestmark = pytest.mark.integration


async def test_root_chat_media_has_exact_grant_source_headers_and_inspection_projection(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat_media(identity_engine)
    request = owned.request
    root = (
        f"/api/v1/operator/accounts/{request.account_id}/chat-image-uploads/"
        f"{request.image_id}/attempts/{request.attempt_id}"
    )
    for kind in OperatorChatMediaKind:
        browser.storage.retained[replace(request, kind=kind).reference] = PRIVATE_CHAT_BYTES
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, owned.images.chat.sender.credential.value)
    denied = await browser.client.get(root + "/original")
    assert denied.status_code == HTTPStatus.FORBIDDEN
    assert not browser.storage.started.is_set()
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, owned.images.owner.credential.value)
    for kind in OperatorChatMediaKind:
        result = await browser.client.get(root + "/" + kind.value)
        assert result.status_code == HTTPStatus.OK
        assert result.content == PRIVATE_CHAT_BYTES
        assert result.headers["Cache-Control"] == "no-store"
        assert result.headers["X-Content-Type-Options"] == "nosniff"
        assert result.headers["Content-Disposition"].startswith("attachment;")
        assert result.headers["Content-Type"] == (
            "application/octet-stream" if kind == OperatorChatMediaKind.ORIGINAL else "image/jpeg"
        )
    async with owned.images.chat.api.sessions() as session:
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
    assert len(audits) == len(OperatorChatMediaKind)
    for audit in audits:
        assert audit.action == "read_chat_media"
        assert audit.requested_chat_owner_id == request.account_id
        assert audit.requested_chat_attempt_id == request.attempt_id
        assert audit.actual_source_image_id == request.image_id
        assert audit.actual_source_upload_id is None
    inspected = await browser.client.get(f"/api/v1/operator/audits/{audits[0].id}")
    assert inspected.status_code == HTTPStatus.OK
    assert inspected.json()["actual_source_image_id"] == str(request.image_id)
    assert inspected.json()["requested_chat_owner_id"] == str(request.account_id)
    assert inspected.json()["actual_source_upload_id"] is None

    async with identity_engine.begin() as connection:
        with pytest.raises(RuntimeError, match="retained chat-media inspection facts"):
            await connection.run_sync(run_revision_step, "0056_operator_chat_media", "downgrade")


@pytest.mark.parametrize("field", ["requested_chat_owner_id", "requested_chat_attempt_id"])
async def test_database_rejects_fabricated_chat_owner_or_attempt_source(
    identity_engine: AsyncEngine,
    field: str,
) -> None:
    owned = await chat_media(identity_engine)
    result = await owned.read()(owned.images.owner.credential, owned.request)
    assert result is not None
    with pytest.raises(IntegrityError):
        async with owned.images.chat.api.sessions.begin() as session:
            await session.execute(update(OperatorAuditRecord).values({field: uuid4()}))
