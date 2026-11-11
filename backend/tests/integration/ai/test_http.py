from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.ai.worker import ExecuteNextJob
from studymate.domain.ai.jobs import Failure
from studymate.domain.ai.tasks import (
    AiResult,
    AiTask,
    ClarifiedGoal,
    Observation,
    PhotoAssessment,
    SubjectSuggestions,
)
from studymate.infrastructure.ai.models import AiJobRecord, AiSlotRecord
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.media_uploads import SqlMediaTransaction
from studymate.presentation.ai import AiHttpServices, ai_router
from studymate.presentation.browser import SESSION_COOKIE, BrowserConfiguration
from studymate.presentation.command_body_limit import JsonCommandBodyLimit
from studymate.presentation.request_errors import validation_problem
from tests.integration.ai.test_queue import Services, services
from tests.integration.catalogue_fixture import subject
from tests.integration.onboarding_fixture import ready_setup
from tests.integration.student_actor import Actor, actor
from tests.unit.ai.test_http import ORIGIN, SIGNER

EXPECTED_JOBS = 2

pytestmark = pytest.mark.integration


@asynccontextmanager
async def client(
    api: Services, owner: Actor, *, runtime_available: bool = True
) -> AsyncIterator[AsyncClient]:
    if not runtime_available:
        async with api.sessions.begin() as session:
            await session.execute(
                update(AiSlotRecord).where(AiSlotRecord.id == 1).values(runtime_state="blocked")
            )
    app = FastAPI()
    app.add_middleware(JsonCommandBodyLimit)
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(
        ai_router(
            AiHttpServices(
                api.submit,
                api.read,
                api.cancel,
                SIGNER,
                BrowserConfiguration(ORIGIN, frozenset({ORIGIN})),
            )
        )
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url=ORIGIN,
        cookies={SESSION_COOKIE: owner.credential.value},
    ) as http:
        http.headers.update(
            {
                "Origin": ORIGIN,
                "X-CSRF-Token": await SIGNER.csrf_token(owner.credential),
                "Idempotency-Key": str(uuid4()),
            }
        )
        yield http


def draft() -> dict[str, object]:
    return {
        "kind": "clarify_goal",
        "source": {"kind": "draft", "id": str(uuid4()), "version": 1},
        "text": "Private synthetic unsaved context",
    }


class Executor:
    async def execute(self, task: AiTask, timeout_seconds: float) -> AiResult:
        assert task.source.version == 1
        assert timeout_seconds > 0
        return ClarifiedGoal("Synthetic clarification")


async def test_http_draft_idempotency_owner_and_typed_fake_result(ai_engine: AsyncEngine) -> None:
    owner = await actor(ai_engine)
    other = await actor(ai_engine)
    api = services(ai_engine)
    body = draft()
    async with client(api, owner) as http:
        created = await http.post("/api/v1/ai/jobs", json=body)
        assert created.status_code == HTTPStatus.ACCEPTED, created.text
        assert (await http.post("/api/v1/ai/jobs", json=body)).json() == created.json()
        conflict = await http.post(
            "/api/v1/ai/jobs", json=body | {"text": "Changed synthetic input"}
        )
        assert conflict.status_code == HTTPStatus.CONFLICT
        location = created.headers["location"]
        async with client(api, other) as foreign:
            assert (await foreign.get(location)).status_code == HTTPStatus.NOT_FOUND
            assert (await foreign.post(location + "/cancel")).status_code == HTTPStatus.NOT_FOUND
        assert await ExecuteNextJob(api.queue, Executor())()
        result = await http.get(location)
        assert result.json()["result"] == {"suggestion": "Synthetic clarification"}
        assert result.json()["state"] == "succeeded"
        assert "Private synthetic" not in result.text
        assert result.json()["source"]["content_hash"]
    async with client(api, owner, runtime_available=False) as disabled:
        assert (await disabled.get(location)).json() == result.json()
        assert (await disabled.post(location + "/cancel")).json() == result.json()
        assert (
            await disabled.post("/api/v1/ai/jobs", json=draft())
        ).status_code == HTTPStatus.SERVICE_UNAVAILABLE
    async with api.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(AiJobRecord)) == 1


async def test_http_cancel_and_live_guard_when_provider_disabled(ai_engine: AsyncEngine) -> None:
    owner = await actor(ai_engine)
    unverified = await actor(ai_engine, verified=False)
    api = services(ai_engine)
    async with client(api, owner) as http:
        created = await http.post("/api/v1/ai/jobs", json=draft())
        location = created.headers["location"]
        cancelled = await http.post(location + "/cancel")
        assert cancelled.json()["state"] == "cancelled"
        assert (await http.post(location + "/cancel")).json() == cancelled.json()
    async with client(api, unverified, runtime_available=False) as http:
        assert (
            await http.post("/api/v1/ai/jobs", json=draft())
        ).status_code == HTTPStatus.FORBIDDEN
    async with api.sessions.begin() as session:
        await session.execute(
            update(AccountRecord).where(AccountRecord.id == owner.id).values(banned_at=func.now())
        )
    async with client(api, owner, runtime_available=False) as http:
        assert (
            await http.post("/api/v1/ai/jobs", json=draft())
        ).status_code == HTTPStatus.FORBIDDEN
        assert (await http.get(location)).status_code == HTTPStatus.FORBIDDEN


async def test_http_quota_circuit_and_missing_source_never_fake_accept(
    ai_engine: AsyncEngine,
) -> None:
    owner = await actor(ai_engine)
    api = services(ai_engine)
    async with client(api, owner) as http:
        missing = draft() | {"source": {"kind": "resource", "id": str(uuid4()), "version": 1}}
        assert (await http.post("/api/v1/ai/jobs", json=missing)).status_code == HTTPStatus.CONFLICT
        for _ in range(2):
            http.headers["Idempotency-Key"] = str(uuid4())
            assert (
                await http.post("/api/v1/ai/jobs", json=draft())
            ).status_code == HTTPStatus.ACCEPTED
        http.headers["Idempotency-Key"] = str(uuid4())
        quota = await http.post("/api/v1/ai/jobs", json=draft())
        assert quota.status_code == HTTPStatus.TOO_MANY_REQUESTS
        assert quota.headers["Retry-After"] == "1"
        running = await api.queue.claim()
        assert running is not None
        await api.queue.complete(running, Failure.AUTH, stopped=True)
        unavailable = await http.post("/api/v1/ai/jobs", json=draft())
        assert unavailable.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert unavailable.headers["Retry-After"] == "1"
    async with api.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(AiJobRecord)) == EXPECTED_JOBS


async def test_http_subject_and_photo_use_actual_sources_and_typed_results(
    ai_engine: AsyncEngine,
) -> None:
    owner = await actor(ai_engine)
    api = services(ai_engine)
    candidate = await subject(ai_engine)
    await ready_setup(ai_engine, owner.credential)
    async with api.sessions() as session:
        photo = await SqlMediaTransaction(session).current_photo(owner.id)
    assert photo is not None
    async with client(api, owner) as http:
        catalogue_body = {
            "kind": "suggest_subject",
            "source": {"kind": "draft", "id": str(uuid4()), "version": 1},
            "label": "Explicit synthetic topic",
            "candidate_ids": [str(candidate.id)],
        }
        created = await http.post("/api/v1/ai/jobs", json=catalogue_body)
        assert created.status_code == HTTPStatus.ACCEPTED, created.text
        running = await api.queue.claim()
        assert running is not None
        await api.queue.complete(running, SubjectSuggestions((candidate.id,)), stopped=True)
        completed = await http.get(created.headers["location"])
        assert completed.json()["kind"] == "suggest_subject"
        assert completed.json()["result"] == {"ids": [str(candidate.id)]}
        http.headers["Idempotency-Key"] = str(uuid4())
        photo_body = {
            "kind": "assess_photo",
            "source": {"kind": "resource", "id": str(photo.upload_id), "version": photo.version},
        }
        created = await http.post("/api/v1/ai/jobs", json=photo_body)
        assert created.status_code == HTTPStatus.ACCEPTED, created.text
        running = await api.queue.claim()
        assert running is not None
        assessment = PhotoAssessment(Observation.UNCERTAIN, Observation.NO, Observation.UNCERTAIN)
        await api.queue.complete(running, assessment, stopped=True)
        completed = await http.get(created.headers["location"])
        assert completed.json()["result"] == {
            "blurred": "uncertain",
            "face_visible": "no",
            "multiple_people": "uncertain",
        }
        assert "reference" not in completed.text
        assert "attempt_id" not in completed.text
