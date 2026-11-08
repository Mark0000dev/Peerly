from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.messaging.goal_shares import ShareCurrentGoalCommand
from studymate.application.profiles.goals import CompleteGoalCommand, CompleteOwnGoal
from studymate.infrastructure.persistence.goals import SqlGoalUnitOfWork
from studymate.infrastructure.security.browser_tokens import HmacBrowserTokenSigner
from studymate.presentation.browser import SESSION_COOKIE, BrowserConfiguration
from studymate.presentation.messaging.goal_shares import GoalSharingHttpServices, goal_shares_router
from studymate.presentation.request_errors import validation_problem
from tests.integration.messaging.goal_share_fixture import command, sharing
from tests.integration.onboarding_fixture import ready_setup
from tests.integration.profile_lifecycle_fixture import complete_existing_setup
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.student_actor import Actor, actor
from tests.integration.test_message_commands import Chat, chat

pytestmark = pytest.mark.integration
ORIGIN = "https://goal-share.test"
SIGNER = HmacBrowserTokenSigner(b"x" * 32)


@asynccontextmanager
async def client(context: Chat, owner: Actor | None = None) -> AsyncIterator[AsyncClient]:
    principal = owner if owner is not None else context.sender
    api = sharing(context)
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(
        goal_shares_router(
            GoalSharingHttpServices(
                api.share, api.history, SIGNER, BrowserConfiguration(ORIGIN, frozenset({ORIGIN}))
            )
        )
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url=ORIGIN,
            cookies={SESSION_COOKIE: principal.credential.value},
        ) as http,
    ):
        http.headers.update(
            {
                "Origin": ORIGIN,
                "X-CSRF-Token": await SIGNER.csrf_token(principal.credential),
                "Idempotency-Key": str(uuid4()),
            }
        )
        yield http


def payload(value: ShareCurrentGoalCommand) -> dict[str, str | int]:
    return {
        "goal_id": str(value.goal_id),
        "expected_goal_version": value.expected_goal_version,
        "expected_context_version": value.expected_context_version,
    }


async def test_actual_goal_share_http_baseline_cas_original_receipt_and_historical_caps(
    identity_engine: AsyncEngine,
) -> None:
    context = await chat(identity_engine)
    submission = await command(context)
    api = sharing(context)
    path = f"/api/v1/conversations/{context.conversation_id}/goal-shares"
    async with client(context) as http:
        baseline = await http.get(path)
        assert baseline.status_code == HTTPStatus.OK, baseline.text
        assert baseline.json()["current_context_version"] == 0
        assert baseline.json()["baseline"]["context_version"] == 0
        assert baseline.json()["latest"] is None
        original_key = http.headers["Idempotency-Key"]
        original = await http.post(path, json=payload(submission))
        assert original.status_code == HTTPStatus.OK, original.text
        assert original.json()["source"]["subject"]["kind"] == "canonical"
        assert "can_complete" not in original.json()
        assert (await http.post(path, json=payload(submission))).json() == original.json()
        assert (await http.get(path)).json()["latest"]["can_complete"]
        other = await api.share(
            await command(context, context.recipient, original.json()["context_version"])
        )
        http.headers["Idempotency-Key"] = str(uuid4())
        conflict = await http.post(path, json=payload(submission))
        assert conflict.status_code == HTTPStatus.CONFLICT
        assert conflict.json()["recovery"]["current_context_version"] == other.context_version
        http.headers["Idempotency-Key"] = str(uuid4())
        current = await command(context, context.sender, other.context_version)
        reshared = await http.post(path, json=payload(current))
        assert reshared.status_code == HTTPStatus.OK, reshared.text
        await CompleteOwnGoal(SqlGoalUnitOfWork(context.api.sessions), HASHER, FINGERPRINTER)(
            CompleteGoalCommand(
                context.sender.credential,
                current.goal_id,
                current.expected_goal_version,
                current.intent_key,
            )
        )
        http.headers["Idempotency-Key"] = original_key
        assert (await http.post(path, json=payload(submission))).json() == original.json()
        historical = await http.get(path)
        assert not any(row["can_complete"] for row in historical.json()["history"])
        assert historical.json()["latest"]["share_id"] == reshared.json()["share_id"]
        assert historical.headers["cache-control"] == "private, no-store"


async def test_goal_share_http_has_no_foreign_source_or_extra_authority_grant(
    identity_engine: AsyncEngine,
) -> None:
    context = await chat(identity_engine)
    other = await actor(identity_engine)
    await ready_setup(identity_engine, other.credential)
    await complete_existing_setup(identity_engine, other)
    submission = await command(context)
    path = f"/api/v1/conversations/{context.conversation_id}/goal-shares"
    async with client(context, other) as foreign:
        assert (await foreign.get(path)).status_code == HTTPStatus.NOT_FOUND
        assert (
            await foreign.post(path, json=payload(submission))
        ).status_code == HTTPStatus.NOT_FOUND
        assert (
            await foreign.get(f"/api/v1/conversations/{uuid4()}/goal-shares")
        ).status_code == HTTPStatus.NOT_FOUND
    async with client(context) as http:
        bad = await http.post(
            path, json={**payload(submission), "context": "Private forged source"}
        )
        assert bad.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert "Private forged" not in bad.text
        assert (
            await http.get(path + "?cursor=invalid")
        ).status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        http.headers["Origin"] = "https://foreign.test"
        assert (await http.post(path, json=payload(submission))).status_code == HTTPStatus.FORBIDDEN
        http.cookies.clear()
        assert (await http.get(path)).status_code == HTTPStatus.UNAUTHORIZED
        assert (
            await http.post(path, json=payload(submission))
        ).status_code == HTTPStatus.UNAUTHORIZED
