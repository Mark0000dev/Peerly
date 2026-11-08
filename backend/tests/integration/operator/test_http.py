from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.identity.registration import (
    BeginRegistrationCommand,
    CompleteRegistrationCommand,
)
from studymate.application.operator.accounts import ReadOperatorAccount, SearchOperatorAccounts
from studymate.application.operator.messages import ReadOperatorConversationMessages
from studymate.domain.operator.audit import OperatorAudit
from studymate.infrastructure.observability.http import JsonHttpObserver
from studymate.infrastructure.observability.tracing import OtelHttpTracing
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.operator.transactions import SqlOperatorUnitOfWork
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.router import OperatorHttpServices, operator_router
from studymate.presentation.request_correlation import RequestCorrelation
from studymate.presentation.request_errors import validation_problem
from studymate.presentation.unexpected_errors import unexpected_problem
from tests.integration.onboarding_fixture import ready_setup
from tests.integration.operator.test_reads import CODEC, HASHER, operator, uow
from tests.integration.registration_fixture import documents
from tests.integration.student_actor import Actor, actor
from tests.integration.test_message_commands import chat
from tests.integration.test_registration import registration

pytestmark = pytest.mark.integration
ROOT = "/api/v1/operator"


@asynccontextmanager
async def client(unit: SqlOperatorUnitOfWork, owner: Actor) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.add_exception_handler(Exception, unexpected_problem)
    app.add_middleware(RequestCorrelation, observer=JsonHttpObserver(), tracing=OtelHttpTracing())
    app.include_router(
        operator_router(
            OperatorHttpServices(
                SearchOperatorAccounts(unit, HASHER, HmacIntentFingerprinter(b"x" * 32), CODEC),
                ReadOperatorAccount(unit, HASHER),
                ReadOperatorConversationMessages(unit, HASHER, CODEC),
            )
        )
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="https://operator.test",
            cookies={SESSION_COOKIE: owner.credential.value},
        ) as http,
    ):
        yield http


async def test_http_retains_registration_profile_sources_with_actual_correlated_audit(
    identity_engine: AsyncEngine,
) -> None:
    owner = await operator(identity_engine)
    target = await actor(identity_engine)
    await ready_setup(identity_engine, target.credential)
    await documents(identity_engine)
    begin, complete, _ = registration(identity_engine)
    context = await begin(BeginRegistrationCommand(target.credential, IntentKey(str(uuid4()))))
    receipt = await complete(
        CompleteRegistrationCommand(target.credential, context.id, IntentKey(str(uuid4())))
    )
    async with client(uow(identity_engine), owner) as http:
        response = await http.get(f"{ROOT}/accounts/{target.id}")
        assert response.status_code == HTTPStatus.OK
        detail = response.json()
        assert detail["registration"]["id"] == str(receipt.id)
        assert detail["registration"]["notice_text"] == context.notice_text
        assert detail["registration"]["terms"]["id"] == str(context.terms.id)
        assert detail["profile"]["display_name"] == "Synthetic student"
        assert detail["photo"]["version"] > 0
        assert detail["goal"]["subject"]["label"] == "Synthetic custom topic"
        assert detail["lifecycle"]["completed_at"] is not None
        for forbidden in ("secret_digest", "sealed", "storage_key", "display_url", "csrf_token"):
            assert forbidden not in response.text
        assert response.headers["Cache-Control"] == "no-store"
    async with async_sessionmaker(identity_engine)() as session:
        audit = (await session.scalars(select(OperatorAuditRecord))).one()
        event = (
            await session.scalars(
                select(ProductEventRecord).where(
                    ProductEventRecord.operator_audit_id == audit.id,
                )
            )
        ).one()
        assert audit.http_request_id is not None
        assert str(audit.http_request_id) == response.headers["X-Request-ID"]
        assert event.request_id == audit.http_request_id
        assert audit.result_ids == [target.id]


async def test_http_missing404_has_committed_audit_not_premature_rollback(
    identity_engine: AsyncEngine,
) -> None:
    owner = await operator(identity_engine)
    async with client(uow(identity_engine), owner) as http:
        response = await http.get(f"{ROOT}/accounts/{uuid4()}")
        assert response.status_code == HTTPStatus.NOT_FOUND
        assert response.json()["code"] == "operator_resource_unavailable"
    async with async_sessionmaker(identity_engine)() as session:
        audit = (await session.scalars(select(OperatorAuditRecord))).one()
        assert audit.outcome == "not_found"
        assert (
            await session.scalars(select(ProductEventRecord))
        ).one().operator_audit_id == audit.id


async def test_http_db_operator_role_is_mandatory_not_cookie_claim(
    identity_engine: AsyncEngine,
) -> None:
    ordinary = await actor(identity_engine)
    async with client(uow(identity_engine), ordinary) as http:
        http.headers["X-Operator"] = "true"
        response = await http.get(ROOT + "/accounts")
        assert response.status_code == HTTPStatus.FORBIDDEN
    async with async_sessionmaker(identity_engine)() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))


async def test_http_nonparticipant_messages_reveal_actual_content_without_case_filter(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    sent = await owned.send()(owned.command())
    assert sent.message is not None
    owner = await operator(identity_engine)
    async with client(uow(identity_engine), owner) as http:
        response = await http.get(f"{ROOT}/conversations/{owned.conversation_id}/messages")
        assert response.status_code == HTTPStatus.OK
        assert response.json()["messages"][0]["text"] == sent.message.content.text
        assert response.json()["messages"][0]["message_id"] == str(sent.message.id)
        assert "case_id" not in response.text


async def test_http_commit_failure_returns_no_target_data_and_leaves_no_audit(
    identity_engine: AsyncEngine,
) -> None:
    owner = await operator(identity_engine)

    async def fail(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        raise RuntimeError("synthetic failure")

    unit = SqlOperatorUnitOfWork(async_sessionmaker(identity_engine, expire_on_commit=False), fail)
    async with client(unit, owner) as http:
        response = await http.get(f"{ROOT}/accounts/{owner.id}")
        assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert response.json()["code"] == "internal_error"
        assert "synthetic-" not in response.text
        assert "google_link" not in response.text
    async with async_sessionmaker(identity_engine)() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
        assert not tuple(await session.scalars(select(ProductEventRecord)))
