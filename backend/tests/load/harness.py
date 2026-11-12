"""Real root-ASGI requests and business storage; controlled executor only."""

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from http import HTTPStatus
from time import perf_counter
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.infrastructure.ai.models import AiIntentRecord, AiJobRecord
from studymate.presentation.ai.models import JobResponse
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.identity import IdentityResponse
from studymate.presentation.profile_models import OwnProfileResponse, ProfileRevisionResponse
from tests.integration.ai.test_saturation import synthetic_accounts
from tests.integration.http_identity import ORIGIN, BrowserHarness, write_headers
from tests.load.measurements import (
    AI_LIMIT_SECONDS,
    CORE_LIMIT_SECONDS,
    MAX_CORE_SAMPLES,
    POPULATION,
    Latency,
    LoadPlan,
    throughput,
)


@dataclass(frozen=True, slots=True)
class Student:
    actor_id: UUID
    source_id: UUID
    cookie: str = field(repr=False)
    csrf: str = field(repr=False)

    def headers(self, key: UUID) -> dict[str, str]:
        return {
            "Cookie": self.cookie,
            "Origin": ORIGIN,
            "X-CSRF-Token": self.csrf,
            "Idempotency-Key": str(key),
        }

    def body(self, tag: str) -> dict[str, object]:
        return {
            "kind": "clarify_goal",
            "source": {"kind": "resource", "id": str(self.source_id), "version": 1},
            "text": "Synthetic bounded load " + tag,
        }


@dataclass(frozen=True, slots=True)
class Accepted:
    student: Student
    key: UUID
    tag: str
    job_id: UUID


async def students(browser: BrowserHarness) -> tuple[Student, ...]:
    accounts = await synthetic_accounts(browser.ai_engine)
    result: list[Student] = []
    # Seeded test sessions establish real database authority. The actual /me
    # endpoint issues each CSRF token; no cookie signer or auth bypass is added.
    for owner, source in accounts:
        cookie = SESSION_COOKIE + "=" + owner.credential.value
        response = await browser.client.get("/api/v1/me", headers={"Cookie": cookie})
        assert response.status_code == HTTPStatus.OK
        identity = IdentityResponse.model_validate(response.json())
        assert identity.account_id == owner.id
        result.append(Student(owner.id, source.id, cookie, identity.csrf_token))
    assert len(result) == POPULATION
    return tuple(result)


async def accepted(browser: BrowserHarness, student: Student, tag: str) -> Accepted:
    key = uuid4()
    response = await browser.client.post(
        "/api/v1/ai/jobs", json=student.body(tag), headers=student.headers(key)
    )
    assert response.status_code == HTTPStatus.ACCEPTED
    return Accepted(student, key, tag, JobResponse.model_validate(response.json()).id)


async def replay(browser: BrowserHarness, command: Accepted) -> None:
    response = await browser.client.post(
        "/api/v1/ai/jobs",
        json=command.student.body(command.tag),
        headers=command.student.headers(command.key),
    )
    assert response.status_code == HTTPStatus.ACCEPTED
    assert JobResponse.model_validate(response.json()).id == command.job_id


async def cancel(browser: BrowserHarness, command: Accepted) -> None:
    response = await browser.client.post(
        f"/api/v1/ai/jobs/{command.job_id}/cancel", headers=command.student.headers(uuid4())
    )
    assert response.status_code == HTTPStatus.OK
    assert JobResponse.model_validate(response.json()).state.value == "cancelled"


async def security_controls(browser: BrowserHarness, command: Accepted, other: Student) -> None:
    missing_origin = command.student.headers(uuid4())
    del missing_origin["Origin"]
    response = await browser.client.post(
        "/api/v1/ai/jobs", json=command.student.body("denied-origin"), headers=missing_origin
    )
    assert response.status_code == HTTPStatus.FORBIDDEN
    missing_csrf = command.student.headers(uuid4())
    del missing_csrf["X-CSRF-Token"]
    response = await browser.client.post(
        "/api/v1/ai/jobs", json=command.student.body("denied-csrf"), headers=missing_csrf
    )
    assert response.status_code == HTTPStatus.FORBIDDEN
    response = await browser.client.get(
        f"/api/v1/ai/jobs/{command.job_id}", headers={"Cookie": other.cookie}
    )
    assert response.status_code == HTTPStatus.NOT_FOUND


@dataclass(slots=True)
class MixedObservation:
    ai_seconds: list[float] = field(default_factory=list)
    core_seconds: list[float] = field(default_factory=list)
    ai_statuses: list[int] = field(default_factory=list)
    active: int = 0
    peak_active: int = 0
    core_commands: int = 0
    core_overlap_samples: int = 0
    elapsed: float = 0.0

    def receipt(self, plan: LoadPlan) -> dict[str, object]:
        ai = Latency.summarize(tuple(self.ai_seconds))
        core = Latency.summarize(tuple(self.core_seconds))
        assert ai.samples == plan.active_users
        assert self.peak_active <= plan.concurrency
        assert ai.maximum_seconds < AI_LIMIT_SECONDS
        assert core.maximum_seconds < CORE_LIMIT_SECONDS
        assert self.core_commands == 1
        assert self.core_overlap_samples > 0
        assert all(status == HTTPStatus.SERVICE_UNAVAILABLE for status in self.ai_statuses)
        return {
            "fixture_student_population": POPULATION,
            "additional_core_http_actor_count": 1,
            "active_student_accounts": plan.active_users,
            "ai_http_workers": plan.concurrency,
            "peak_ai_requests_in_flight": self.peak_active,
            "ai_http_attempts": ai.samples,
            "ai_http_503": len(self.ai_statuses),
            "ai_http_p95_seconds": ai.p95_seconds,
            "ai_http_max_seconds": ai.maximum_seconds,
            "core_http_samples": core.samples,
            "core_http_p95_seconds": core.p95_seconds,
            "core_http_max_seconds": core.maximum_seconds,
            "core_profile_commands": self.core_commands,
            "core_overlap_samples": self.core_overlap_samples,
            "measured_wall_seconds": self.elapsed,
            "ai_http_attempts_per_second": throughput(ai.samples, self.elapsed),
        }


async def core_mix(
    browser: BrowserHarness, stop: asyncio.Event, measured: MixedObservation
) -> None:
    payload = {"display_name": "Synthetic load student", "languages": ["en"], "expected_version": 0}
    headers = await write_headers(browser.client)
    started = perf_counter()
    response = await browser.client.put("/api/v1/me/profile", json=payload, headers=headers)
    measured.core_seconds.append(perf_counter() - started)
    assert response.status_code == HTTPStatus.OK
    saved = ProfileRevisionResponse.model_validate(response.json())
    measured.core_commands += 1
    while not stop.is_set() and len(measured.core_seconds) < MAX_CORE_SAMPLES:
        for route in ("/api/v1/me", "/api/v1/me/profile", "/api/ready"):
            started = perf_counter()
            response = await browser.client.get(route)
            measured.core_seconds.append(perf_counter() - started)
            assert response.status_code == HTTPStatus.OK
            if measured.active:
                measured.core_overlap_samples += 1
        with suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=0.05)
    # Immutable replay is checked after load as well as readback; the profile
    # command must not disappear or spend another version.
    response = await browser.client.put("/api/v1/me/profile", json=payload, headers=headers)
    assert response.status_code == HTTPStatus.OK
    assert ProfileRevisionResponse.model_validate(response.json()) == saved
    response = await browser.client.get("/api/v1/me/profile")
    assert OwnProfileResponse.model_validate(response.json()).profile == saved


async def mixed_http(
    browser: BrowserHarness, population: tuple[Student, ...], plan: LoadPlan
) -> MixedObservation:
    measured = MixedObservation()
    stop = asyncio.Event()
    pending = iter(population[: plan.active_users])

    async def worker() -> None:
        # next() occurs without an await: each actor is assigned once, with only
        # the configured number of tasks rather than one task per account.
        for student in pending:
            measured.active += 1
            measured.peak_active = max(measured.peak_active, measured.active)
            started = perf_counter()
            try:
                response = await browser.client.post(
                    "/api/v1/ai/jobs",
                    json=student.body("measured"),
                    headers=student.headers(uuid4()),
                )
                measured.ai_statuses.append(response.status_code)
            finally:
                measured.ai_seconds.append(perf_counter() - started)
                measured.active -= 1

    async def traffic() -> None:
        try:
            async with asyncio.TaskGroup() as group:
                for _ in range(plan.concurrency):
                    group.create_task(worker())
        finally:
            stop.set()

    started = perf_counter()
    async with asyncio.TaskGroup() as group:
        group.create_task(core_mix(browser, stop, measured))
        group.create_task(traffic())
    measured.elapsed = perf_counter() - started
    return measured


async def reconcile(
    sessions: async_sessionmaker[AsyncSession], commands: tuple[Accepted, ...]
) -> None:
    async with sessions() as session:
        jobs = tuple(await session.scalars(select(AiJobRecord)))
        intents = tuple(await session.scalars(select(AiIntentRecord)))
    assert {row.id for row in jobs} == {command.job_id for command in commands}
    assert {(row.actor_id, row.key, row.job_id) for row in intents} == {
        (command.student.actor_id, str(command.key), command.job_id) for command in commands
    }
