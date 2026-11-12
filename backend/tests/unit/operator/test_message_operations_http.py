from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from uuid import UUID

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from studymate.application.operator.message_operations import ReadOperatorMessageOperation
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.message_operations_router import (
    OperatorMessageOperationsHttpServices,
    operator_message_operations_router,
)
from tests.unit.identity_store import CREDENTIAL
from tests.unit.operator.message_operations_store import OperationsStore
from tests.unit.operator.store import TARGET
from tests.unit.operator.test_authorized_reads import HASHER
from tests.unit.operator.test_message_operations import reader

ROOT = f"/api/v1/operator/accounts/{TARGET}/message-operations"


@asynccontextmanager
async def client(store: OperationsStore) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.include_router(
        operator_message_operations_router(
            OperatorMessageOperationsHttpServices(
                reader(store), ReadOperatorMessageOperation(store, HASHER)
            )
        )
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://operator.test",
        cookies={SESSION_COOKIE: CREDENTIAL.value},
    ) as http:
        yield http


async def test_private_terminal_operation_list_and_detail() -> None:
    store = OperationsStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        listing = await http.get(ROOT)
        assert listing.status_code == HTTPStatus.OK
        assert listing.headers["Cache-Control"] == "no-store"
        assert listing.headers["Referrer-Policy"] == "no-referrer"
        detail = await http.get(ROOT + f"/{UUID(int=2)}")
        assert detail.status_code == HTTPStatus.OK
        assert detail.json()["message"]["text"] == "  private retained text  "
        cancelled = await http.get(ROOT + f"/{UUID(int=3)}")
        assert cancelled.json()["message"] is None
        assert cancelled.json()["state"] == "cancelled"
        assert "storage_key" not in detail.text
        assert "secret_digest" not in detail.text


async def test_no_implicit_operator_and_no_cookie_only_authority() -> None:
    store = OperationsStore()
    async with client(store) as http:
        assert (await http.get(ROOT)).status_code == HTTPStatus.FORBIDDEN
        http.cookies.clear()
        assert (await http.get(ROOT)).status_code == HTTPStatus.UNAUTHORIZED
    assert store.private_queries == 0
    assert not store.audit
