"""Root wiring for retained conversation discovery uses actual operator authority."""

from http import HTTPStatus
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.presentation.browser import SESSION_COOKIE
from tests.integration.http_identity import BrowserHarness
from tests.integration.operator.test_reads import operator
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration


async def test_root_conversation_index_denies_student_and_audits_actual_operator_reads(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    student = await actor(identity_engine)
    path = f"/api/v1/operator/accounts/{student.id}/conversations"
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, student.credential.value)
    denied = await browser.client.get(path)
    assert denied.status_code == HTTPStatus.FORBIDDEN
    owner = await operator(identity_engine)
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, owner.credential.value)
    empty = await browser.client.get(path)
    assert empty.status_code == HTTPStatus.OK
    assert empty.json() == {"account_id": str(student.id), "conversations": [], "next_cursor": None}
    missing = uuid4()
    unavailable = await browser.client.get(f"/api/v1/operator/accounts/{missing}/conversations")
    assert unavailable.status_code == HTTPStatus.NOT_FOUND
    for response in (denied, empty, unavailable):
        assert response.headers["Cache-Control"] == "no-store"
    async with async_sessionmaker(identity_engine)() as session:
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
    assert len(audits) == len((student.id, missing))
    assert {row.requested_id for row in audits} == {student.id, missing}
    assert {row.action for row in audits} == {"read_account"}
    assert {row.outcome for row in audits} == {"read", "not_found"}
