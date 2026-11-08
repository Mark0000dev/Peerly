from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from http import HTTPStatus
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from pydantic import TypeAdapter, ValidationError

from studymate.application.ai.ports import AiUnavailableError
from studymate.application.ai.student import CancelStudentJob, ReadStudentJob
from studymate.application.errors import StorageUnavailableError
from studymate.application.idempotency import IntentKey
from studymate.domain.ai.jobs import AiJob, Failure, JobState
from studymate.domain.ai.tasks import Source, TriageReport
from studymate.infrastructure.security.browser_tokens import HmacBrowserTokenSigner
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from studymate.presentation.ai import AiHttpServices, ai_router
from studymate.presentation.ai.models import CreateJobRequest
from studymate.presentation.browser import SESSION_COOKIE, BrowserConfiguration
from studymate.presentation.command_body_limit import JsonCommandBodyLimit
from studymate.presentation.request_errors import validation_problem
from tests.unit.ai.test_student import Store, request, submit
from tests.unit.identity_store import CREDENTIAL

ORIGIN = "https://app.test"
SIGNER = HmacBrowserTokenSigner(b"x" * 32)
ADAPTER = TypeAdapter(CreateJobRequest)


def payload() -> dict[str, object]:
    return {
        "kind": "clarify_goal",
        "source": {"kind": "resource", "id": str(uuid4()), "version": 1},
        "text": "Synthetic private context",
    }


@asynccontextmanager
async def client(store: Store, *, accepting: bool = True) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.add_middleware(JsonCommandBodyLimit)
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(
        ai_router(
            AiHttpServices(
                submit(store),
                ReadStudentJob(store, Sha256SessionHasher()),
                CancelStudentJob(store, Sha256SessionHasher()),
                SIGNER,
                BrowserConfiguration(ORIGIN, frozenset({ORIGIN})),
                accepting,
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


async def test_create_read_cancel_safe_projection() -> None:
    store = Store()
    async with client(store) as http:
        created = await http.post("/api/v1/ai/jobs", json=payload())
        assert created.status_code == HTTPStatus.ACCEPTED, created.text
        assert created.headers["cache-control"] == "no-store"
        data = created.json()
        assert set(data) == {
            "id",
            "kind",
            "source",
            "target",
            "state",
            "created_at",
            "deadline",
            "result",
            "failure",
            "poll_after_ms",
        }
        assert "Synthetic private" not in created.text
        location = created.headers["location"]
        assert (await http.get(location)).json() == data
        cancelled = await http.post(location + "/cancel")
        assert cancelled.status_code == HTTPStatus.OK
        assert cancelled.json()["state"] == "cancelled"
        assert (await http.post(location + "/cancel")).json() == cancelled.json()
        assert (
            await http.get("/api/v1/ai/jobs/" + str(uuid4()))
        ).status_code == HTTPStatus.NOT_FOUND


async def test_disabled_authenticates_live_actor_and_never_admits() -> None:
    store = Store()
    async with client(store, accepting=False) as http:
        unavailable = await http.post("/api/v1/ai/jobs", json=payload())
        assert unavailable.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert unavailable.headers["retry-after"] == "1"
        assert not store.jobs
        store.clock = store.actor.session.expires_at
        assert (
            await http.post("/api/v1/ai/jobs", json=payload())
        ).status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.parametrize(
    ("header", "value", "status"),
    [
        ("Origin", "https://evil.test", 403),
        ("X-CSRF-Token", "wrong", 403),
        ("Idempotency-Key", "x", 422),
    ],
)
async def test_public_browser_write_guards(header: str, value: str, status: int) -> None:
    store = Store()
    async with client(store) as http:
        http.headers[header] = value
        response = await http.post("/api/v1/ai/jobs", json=payload())
        assert response.status_code == status
        assert not store.jobs


@pytest.mark.parametrize(
    "changes",
    [
        {"kind": "triage_report"},
        {"system": "PRIVATE"},
        {"model": "PRIVATE"},
        {"text": "x" * 241},
        {"text": "private\x00"},
        {"source": {"id": str(uuid4()), "version": 1}},
        {"source": {"kind": "draft", "id": str(uuid4()), "version": True}},
        {"source": {"kind": "draft", "id": str(uuid4()), "version": 1, "content_hash": "a" * 64}},
    ],
)
async def test_strict_inputs_are_safe_validation_errors(changes: dict[str, object]) -> None:
    store = Store()
    async with client(store) as http:
        response = await http.post("/api/v1/ai/jobs", json=payload() | changes)
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert "PRIVATE" not in response.text
        assert "<b>" not in response.text
        assert not store.jobs


def test_tagged_drafts_and_catalogue_boundaries() -> None:
    draft = {"kind": "draft", "id": str(uuid4()), "version": 1}
    assert (
        ADAPTER.validate_python(payload() | {"source": draft}).submission().source.kind == "draft"
    )
    candidate = str(uuid4())
    valid = {
        "kind": "suggest_subject",
        "source": draft,
        "label": "Synthetic topic",
        "candidate_ids": [candidate],
    }
    assert ADAPTER.validate_python(valid).submission().label == "Synthetic topic"
    for invalid in [
        valid | {"label": None},
        valid | {"candidate_ids": [candidate, candidate]},
        {"kind": "assess_photo", "source": draft},
        payload() | {"target": "topic", "text": "x" * 81},
    ]:
        with pytest.raises(ValidationError):
            ADAPTER.validate_python(invalid)


def test_retry_configuration_is_bounded() -> None:
    store = Store()
    services = AiHttpServices(
        submit(store),
        ReadStudentJob(store, Sha256SessionHasher()),
        CancelStudentJob(store, Sha256SessionHasher()),
        SIGNER,
        BrowserConfiguration(ORIGIN, frozenset({ORIGIN})),
    )
    assert not services.accepting
    with pytest.raises(ValueError, match="bounded"):
        replace(services, retry_after_seconds=0)


async def test_missing_cookie_is_unauthenticated_for_all_routes() -> None:
    async with client(Store()) as http:
        http.cookies.clear()
        assert (
            await http.post("/api/v1/ai/jobs", json=payload())
        ).status_code == HTTPStatus.UNAUTHORIZED
        location = "/api/v1/ai/jobs/" + str(uuid4())
        assert (await http.get(location)).status_code == HTTPStatus.UNAUTHORIZED
        assert (await http.post(location + "/cancel")).status_code == HTTPStatus.UNAUTHORIZED


def test_factory_openapi_limits_public_kinds_and_requires_source_tag() -> None:
    store = Store()
    app = FastAPI()
    app.add_middleware(JsonCommandBodyLimit)
    app.include_router(
        ai_router(
            AiHttpServices(
                submit(store),
                ReadStudentJob(store, Sha256SessionHasher()),
                CancelStudentJob(store, Sha256SessionHasher()),
                SIGNER,
                BrowserConfiguration(ORIGIN, frozenset({ORIGIN})),
            )
        )
    )
    schema = app.openapi()
    assert set(schema["paths"]) == {
        "/api/v1/ai/jobs",
        "/api/v1/ai/jobs/{job_id}",
        "/api/v1/ai/jobs/{job_id}/cancel",
    }
    source = schema["components"]["schemas"]["DraftSourceRequest"]
    assert "kind" in source["required"]
    assert not source["additionalProperties"]
    assert "content_hash" not in source["properties"]
    create = schema["paths"]["/api/v1/ai/jobs"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    assert set(create["discriminator"]["mapping"]) == {
        "clarify_goal",
        "suggest_subject",
        "assess_photo",
    }


async def test_shared_body_guard_bounds_before_parsing_and_cancel_is_bodyless() -> None:
    store = Store()
    async with client(store) as http:
        missing_type = await http.post("/api/v1/ai/jobs", content=b"{}")
        assert missing_type.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
        oversized = await http.post(
            "/api/v1/ai/jobs", content=b" " * 8193, headers={"Content-Type": "application/json"}
        )
        assert oversized.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
        created = await http.post("/api/v1/ai/jobs", json=payload())
        invalid_cancel = await http.post(created.headers["location"] + "/cancel", json={})
        assert invalid_cancel.status_code == HTTPStatus.BAD_REQUEST
        assert (await http.get(created.headers["location"])).json()["state"] == "queued"


async def test_internal_triage_cannot_escape_student_projection() -> None:
    store = Store()
    created = await submit(store)(CREDENTIAL, request(), IntentKey(str(uuid4())))
    store.jobs[created.id] = replace(
        created, task=TriageReport(Source(uuid4(), 1), "Private internal evidence")
    )
    async with client(store) as http:
        location = "/api/v1/ai/jobs/" + str(created.id)
        for response in [await http.get(location), await http.post(location + "/cancel")]:
            assert response.status_code == HTTPStatus.NOT_FOUND
            assert "Private internal" not in response.text


async def test_terminal_failure_projects_only_bounded_failure_and_no_poll() -> None:
    store = Store()
    created = await submit(store)(CREDENTIAL, request(), IntentKey(str(uuid4())))
    store.jobs[created.id] = replace(created, state=JobState.FAILED, failure=Failure.INVALID_OUTPUT)
    async with client(store) as http:
        response = await http.get("/api/v1/ai/jobs/" + str(created.id))
        assert response.json()["failure"] == "invalid_output"
        assert response.json()["poll_after_ms"] is None
        assert response.json()["result"] is None


class UnavailableStore(Store):
    async def owned(self, actor_id: UUID, job_id: UUID, *, cancel: bool = False) -> AiJob:
        assert actor_id == self.actor.session.account_id
        assert job_id != UUID(int=0)
        if cancel:
            raise AiUnavailableError("Private backend error")
        raise StorageUnavailableError("Private database error")


async def test_storage_and_admission_errors_have_safe_retry_contract() -> None:
    async with client(UnavailableStore()) as http:
        location = "/api/v1/ai/jobs/" + str(uuid4())
        for response in [await http.get(location), await http.post(location + "/cancel")]:
            assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
            assert response.headers["Retry-After"] == "1"
            assert "Private" not in response.text
            assert response.headers["Cache-Control"] == "no-store"
