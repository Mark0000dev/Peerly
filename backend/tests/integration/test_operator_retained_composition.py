"""Root composition of the eight retained reads; no student-authority widening."""

from http import HTTPStatus
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.errors import StorageUnavailableError
from studymate.domain.operator.audit import OperatorAudit
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.operator.transactions import SqlOperatorTransaction
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.presentation.browser import SESSION_COOKIE
from tests.integration.http_identity import BrowserHarness
from tests.integration.operator.test_chat_image_metadata import prepared as image_fixture
from tests.integration.operator.test_connection_requests import prepared as request_fixture
from tests.integration.operator.test_peer_feedback import prepared as feedback_fixture
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration
ROOT = "/api/v1/operator/accounts"


async def assert_inspections(engine: AsyncEngine, account_id: UUID, count: int) -> None:
    async with async_sessionmaker(engine)() as session:
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
        events = tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        )
    assert len(audits) == count
    assert all(row.action == "read_account" and row.requested_id == account_id for row in audits)
    assert {row.operator_audit_id for row in events} == {row.id for row in audits}


async def test_eight_root_reads_require_operator_before_child_lookup(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    student = await actor(identity_engine)
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, student.credential.value)
    prefix = f"{ROOT}/{student.id}"
    paths = (
        "/connection-requests",
        f"/connection-requests/{uuid4()}/history",
        f"/connection-requests/{uuid4()}/disclosures",
        "/chat-image-uploads",
        f"/chat-image-uploads/{uuid4()}/history",
        "/peer-feedback",
        f"/peer-feedback/{uuid4()}/history",
        f"/peer-feedback/{uuid4()}/removals",
    )
    for path in paths:
        response = await browser.client.get(prefix + path)
        assert response.status_code == HTTPStatus.FORBIDDEN
        assert response.headers["Cache-Control"] == "no-store"
    async with async_sessionmaker(identity_engine)() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))


async def test_root_retained_requests_and_disclosures_audit_deleted_target(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    owned = await request_fixture(identity_engine)
    async with owned.uow.sessions.begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == owned.sender.id)
            .values(deleted_at=func.clock_timestamp())
        )
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, owned.owner.credential.value)
    root = f"{ROOT}/{owned.sender.id}/connection-requests"
    listing = await browser.client.get(root)
    assert listing.status_code == HTTPStatus.OK
    assert str(owned.request.id) in listing.text
    history = await browser.client.get(f"{root}/{owned.request.id}/history")
    assert history.status_code == HTTPStatus.OK
    disclosures = await browser.client.get(f"{root}/{owned.request.id}/disclosures")
    assert disclosures.status_code == HTTPStatus.OK
    for response in (listing, history, disclosures):
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["X-Request-ID"]
    await assert_inspections(identity_engine, owned.sender.id, 3)


async def test_root_chat_image_metadata_survives_deletion_without_binary_grant(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    owned = await image_fixture(identity_engine)
    async with owned.uow.sessions.begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == owned.image.account_id)
            .values(deleted_at=func.clock_timestamp())
        )
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, owned.owner.credential.value)
    root = f"{ROOT}/{owned.image.account_id}/chat-image-uploads"
    listing = await browser.client.get(root)
    assert listing.status_code == HTTPStatus.OK
    assert listing.json()["uploads"][0]["id"] == str(owned.image.id)
    history = await browser.client.get(f"{root}/{owned.image.id}/history")
    assert history.status_code == HTTPStatus.OK
    assert history.json()["upload"]["source_metadata"] == "declared_not_object_verified"
    assert "signed" not in history.text
    await assert_inspections(identity_engine, owned.image.account_id, 2)


async def test_root_feedback_histories_are_privileged_retained_reads(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    owned = await feedback_fixture(identity_engine)
    target = owned.revision.reviewer_id
    async with owned.uow.sessions.begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == target)
            .values(deleted_at=func.clock_timestamp())
        )
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, owned.owner.credential.value)
    root = f"{ROOT}/{target}/peer-feedback"
    listing = await browser.client.get(root)
    assert listing.status_code == HTTPStatus.OK
    assert str(owned.revision.id) in listing.text
    history = await browser.client.get(f"{root}/{owned.revision.id}/history")
    assert history.status_code == HTTPStatus.OK
    removals = await browser.client.get(f"{root}/{owned.revision.id}/removals")
    assert removals.status_code == HTTPStatus.OK
    assert removals.json()["removals"] == []
    await assert_inspections(identity_engine, target, 3)


async def test_root_retained_inspection_does_not_escape_failed_canonical_audit(
    browser: BrowserHarness, identity_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    owned = await request_fixture(identity_engine)
    original = SqlOperatorTransaction.save_operator_audit

    async def fail(transaction: SqlOperatorTransaction, audit: OperatorAudit) -> None:
        await original(transaction, audit)
        raise StorageUnavailableError

    monkeypatch.setattr(SqlOperatorTransaction, "save_operator_audit", fail)
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, owned.owner.credential.value)
    response = await browser.client.get(f"{ROOT}/{owned.sender.id}/connection-requests")
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.headers["Retry-After"] == "1"
    assert str(owned.request.id) not in response.text
    await assert_inspections(identity_engine, owned.sender.id, 0)
