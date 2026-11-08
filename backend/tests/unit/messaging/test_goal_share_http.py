from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from http import HTTPStatus
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from studymate.application.messaging.goal_shares import ReadGoalShares
from studymate.infrastructure.messaging.goal_share_cursors import FernetGoalShareCursorCodec
from studymate.infrastructure.security.browser_tokens import HmacBrowserTokenSigner
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from studymate.presentation.browser import SESSION_COOKIE, BrowserConfiguration
from studymate.presentation.messaging.goal_shares import (
    ConversationGoalShareBaselineResponse,
    ConversationGoalShareEntryResponse,
    ConversationGoalSharePageResponse,
    ConversationGoalShareReceiptResponse,
    GoalSharingHttpServices,
    SharedCanonicalSubjectResponse,
    SharedCustomSubjectResponse,
    SharedGoalSourceResponse,
    goal_shares_router,
)
from studymate.presentation.request_errors import validation_problem
from tests.unit.identity_store import CREDENTIAL
from tests.unit.messaging.test_goal_shares import GoalStore, share

ORIGIN = "https://goal-sharing.test"
SIGNER = HmacBrowserTokenSigner(b"x" * 32)
RESPONSE_TYPES: tuple[type[BaseModel], ...] = (
    ConversationGoalShareBaselineResponse,
    ConversationGoalShareEntryResponse,
    ConversationGoalSharePageResponse,
    ConversationGoalShareReceiptResponse,
    SharedCanonicalSubjectResponse,
    SharedCustomSubjectResponse,
    SharedGoalSourceResponse,
)


@asynccontextmanager
async def client(store: GoalStore) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(
        goal_shares_router(
            GoalSharingHttpServices(
                share(store),
                ReadGoalShares(
                    store, Sha256SessionHasher(), FernetGoalShareCursorCodec.from_key(b"x" * 32)
                ),
                SIGNER,
                BrowserConfiguration(ORIGIN, frozenset({ORIGIN})),
            )
        )
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url=ORIGIN,
        cookies={SESSION_COOKIE: CREDENTIAL.value},
    ) as http:
        http.headers.update(
            {
                "Origin": ORIGIN,
                "X-CSRF-Token": await SIGNER.csrf_token(CREDENTIAL),
                "Idempotency-Key": str(uuid4()),
            }
        )
        yield http


async def test_unmounted_goal_share_http_custom_source_baseline_and_original_receipt() -> None:
    store = GoalStore()
    command = store.command()
    path = f"/api/v1/conversations/{command.conversation_id}/goal-shares"
    body = {
        "goal_id": str(command.goal_id),
        "expected_goal_version": command.expected_goal_version,
        "expected_context_version": 0,
    }
    async with client(store) as http:
        baseline = await http.get(path)
        assert baseline.status_code == HTTPStatus.OK
        assert baseline.json()["current_context_version"] == 0
        assert baseline.json()["baseline"]["context_version"] == 0
        assert baseline.json()["history"] == []
        shared = await http.post(path, json=body)
        assert shared.status_code == HTTPStatus.OK, shared.text
        assert shared.json()["source"]["subject"]["kind"] == "custom"
        assert "id" not in shared.json()["source"]["subject"]
        assert shared.json()["source"]["shared_learning"] is False
        assert "can_complete" not in shared.json()
        current = await http.get(path)
        assert current.json()["latest"]["can_complete"] is True
        assert current.json()["latest"]["context_version"] == shared.json()["context_version"]
        store.memory.goals[store.actor.session.account_id] = None
        assert (await http.post(path, json=body)).json() == shared.json()
        http.headers["Idempotency-Key"] = str(uuid4())
        assert (await http.post(path, json=body)).status_code == HTTPStatus.CONFLICT
        historical = await http.get(path)
        assert historical.json()["latest"]["can_complete"] is False


async def test_goal_share_http_rejects_private_authority_and_browser_guards() -> None:
    store = GoalStore()
    command = store.command()
    path = f"/api/v1/conversations/{command.conversation_id}/goal-shares"
    body = {
        "goal_id": str(command.goal_id),
        "expected_goal_version": command.expected_goal_version,
        "expected_context_version": 0,
    }
    async with client(store) as http:
        invalid = await http.post(path, json={**body, "context": "Private forged context"})
        assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert "Private forged" not in invalid.text
        invalid = await http.post(path, json={**body, "expected_goal_version": True})
        assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert (
            await http.get(path + "?cursor=invalid")
        ).status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert store.access is not None
        store.access = replace(store.access, blocked=True)
        assert (await http.post(path, json=body)).status_code == HTTPStatus.CONFLICT
        http.headers["Origin"] = "https://foreign.test"
        assert (await http.post(path, json=body)).status_code == HTTPStatus.FORBIDDEN
        http.cookies.clear()
        assert (await http.get(path)).status_code == HTTPStatus.UNAUTHORIZED
        assert (await http.post(path, json=body)).status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.parametrize("response_type", RESPONSE_TYPES)
def test_goal_share_schema_names_are_specific_and_nested_objects_closed(
    response_type: type[BaseModel],
) -> None:
    schema = response_type.model_json_schema()
    assert schema["additionalProperties"] is False
    definitions = schema.get("$defs")
    if isinstance(definitions, dict):
        for definition in definitions.values():
            if isinstance(definition, dict) and definition.get("type") == "object":
                assert definition["additionalProperties"] is False


async def test_goal_share_http_context_cas_preserves_other_partners_source() -> None:
    store = GoalStore()
    command = store.command()
    first = await share(store)(command)
    peer = GoalStore(store.memory, UUID(int=3))
    current = await share(peer)(peer.command(first.context_version))
    path = f"/api/v1/conversations/{command.conversation_id}/goal-shares"
    async with client(store) as http:
        conflict = await http.post(
            path,
            json={
                "goal_id": str(command.goal_id),
                "expected_goal_version": command.expected_goal_version,
                "expected_context_version": 0,
            },
        )
        assert conflict.status_code == HTTPStatus.CONFLICT
        assert conflict.json()["recovery"]["current_context_version"] == current.context_version
        assert store.memory.shares[-1] == current
