from http import HTTPStatus

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.conversation_index_router import (
    OperatorConversationIndexHttpServices,
    operator_conversation_index_router,
)
from tests.unit.identity_store import CREDENTIAL
from tests.unit.operator.conversation_index_store import ConversationIndexStore
from tests.unit.operator.conversation_index_test import reader, summary
from tests.unit.operator.store import TARGET


async def test_read_factory_requires_cookie_and_actual_operator_and_returns_only_metadata() -> None:
    store = ConversationIndexStore()
    store.rows = (summary(0),)
    app = FastAPI()
    app.include_router(
        operator_conversation_index_router(OperatorConversationIndexHttpServices(reader(store)))
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://operator.test"
    ) as client:
        path = f"/api/v1/operator/accounts/{TARGET}/conversations"
        assert (await client.get(path)).status_code == HTTPStatus.UNAUTHORIZED
        client.cookies.set(SESSION_COOKIE, CREDENTIAL.value)
        assert (await client.get(path)).status_code == HTTPStatus.FORBIDDEN
        store.assign_explicit_operator()
        found = await client.get(path)
        assert found.status_code == HTTPStatus.OK
        assert found.headers["cache-control"] == "no-store"
        assert set(found.json()["conversations"][0]) == {
            "id",
            "relationship_id",
            "low_id",
            "high_id",
            "request_id",
            "accepted_request_version",
        }
        assert "created_at" not in found.text
        assert "next_message_sequence" not in found.text
