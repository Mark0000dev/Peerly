from http import HTTPStatus

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.presentation.browser import SESSION_COOKIE
from tests.integration.http_identity import BrowserHarness
from tests.integration.operator.test_media_http import path
from tests.integration.operator.test_media_read import PRIVATE_BINARY, prepared

pytestmark = pytest.mark.integration
EXPECTED_PHOTO_INSPECTIONS = 4


async def test_root_operator_inspects_retained_photo_metadata_and_bytes_after_deletion(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    api = await prepared(identity_engine)
    browser.storage.retained.update(api.reader.objects)
    async with api.uow.sessions.begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == api.target.id)
            .values(deleted_at=func.clock_timestamp())
        )
    caplog.set_level("INFO", logger="studymate.http")
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, api.owner.credential.value)
    root = f"/api/v1/operator/accounts/{api.target.id}/photo-uploads"
    listing = await browser.client.get(root)
    assert listing.status_code == HTTPStatus.OK
    assert [row["id"] for row in listing.json()["uploads"]] == [str(api.request.upload_id)]
    history = await browser.client.get(f"{root}/{api.request.upload_id}/history")
    assert history.status_code == HTTPStatus.OK
    assert history.json()["attempts_current"][0]["id"] == str(api.request.attempt_id)
    for kind, content_type in (("original", "application/octet-stream"), ("display", "image/jpeg")):
        response = await browser.client.get(path(api, kind))
        assert response.status_code == HTTPStatus.OK
        assert response.content == PRIVATE_BINARY
        assert response.headers["content-type"] == content_type
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["content-disposition"].startswith("attachment;")
        assert response.headers["x-request-id"]
    async with api.uow.sessions() as session:
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
        assert len(audits) == EXPECTED_PHOTO_INSPECTIONS
        media = tuple(audit for audit in audits if audit.action == "read_media")
        assert {audit.requested_media_kind for audit in media} == {"original", "display"}
        assert all(audit.actual_source_upload_id == api.request.upload_id for audit in media)
        canonical = tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        )
        assert {event.operator_audit_id for event in canonical} == {audit.id for audit in audits}
    assert PRIVATE_BINARY.decode() not in caplog.text
