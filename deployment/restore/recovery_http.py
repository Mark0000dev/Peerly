"""Synthetic-only restored root HTTP contracts; no provider or executor success claim."""

import asyncio
import hashlib
import os
import re
import stat
from dataclasses import dataclass, field
from datetime import datetime
from http import HTTPStatus
from pathlib import Path
from uuid import UUID

from deployment.restore.accept_restore import MAX_OBJECT_BYTES, RejectedError
from deployment.restore.recovery_checks import target_guard
from httpx2 import AsyncClient, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.identity.sessions import SessionCredential
from studymate.application.media.storage import MediaObjectMissingError, UploadAccess
from studymate.domain.media import MediaObjectKind, MediaObjectRef
from studymate.infrastructure.media.s3 import object_key
from studymate.presentation.ai.models import JobResponse
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.identity import IdentityResponse
from studymate.presentation.operator.models import OperatorAccountDetailResponse

ORIGIN = "https://recovery.invalid"
HTTP_SECONDS = 5
EXPECTED_AUDITS = 3
DISTINCT_AUTHORITIES = 5
MAX_READS = 8
MAX_STATE_ROWS = 32
TABLES = ("ai_jobs", "ai_intents", "ai_attempts", "ai_executor_slot")


class RecoveryHttpError(RejectedError):
    """Closed codes only; never attach private HTTP responses or credentials."""


@dataclass(frozen=True, slots=True)
class Principal:
    account: UUID
    credential: SessionCredential = field(repr=False)


@dataclass(frozen=True, slots=True)
class RecoveryCase:
    source: str
    target: str
    owner: Principal
    other: Principal
    operator: Principal
    expired: Principal
    revoked: Principal
    deleted: Principal
    revoked_operator: Principal
    photo: UUID
    attempt: UUID
    queued_job: UUID
    running_job: UUID
    display_sha256: str
    display_size: int
    synthetic_not_real_backup: bool = False

    def guard(self, engine: AsyncEngine) -> None:
        target_guard(self.source, self.target)
        if (
            self.synthetic_not_real_backup is not True
            or re.fullmatch(r"peerly_http_source_[0-9a-f]{32}_test", self.source) is None
            or engine.url.password is not None
            or engine.url.drivername != "postgresql+asyncpg"
            or engine.url.host not in {"127.0.0.1", "::1"}
            or engine.url.database != self.target
            or engine.url.query
        ):
            raise RecoveryHttpError("synthetic_owned_database_required")
        expect(
            len(
                {
                    self.owner.account,
                    self.other.account,
                    self.operator.account,
                    self.deleted.account,
                    self.revoked_operator.account,
                }
            )
            == DISTINCT_AUTHORITIES,
            "fixture_authority_collision",
        )
        expect(re.fullmatch(r"[0-9a-f]{64}", self.display_sha256) is not None, "fixture_digest")
        expect(0 < self.display_size <= MAX_OBJECT_BYTES, "fixture_media_size")
        credentials = tuple(
            principal.credential.value
            for principal in (
                self.owner,
                self.other,
                self.operator,
                self.expired,
                self.revoked,
                self.deleted,
                self.revoked_operator,
            )
        )
        if len(set(credentials)) != len(credentials) or self.queued_job == self.running_job:
            raise RecoveryHttpError("fixture_identity_collision")


@dataclass(slots=True)
class RestoredMedia:
    root: Path
    expected: dict[str, tuple[int, str]] = field(repr=False)
    reads: int = 0

    async def read(self, reference: MediaObjectRef) -> bytes:
        if self.reads >= MAX_READS or reference.kind == MediaObjectKind.UPLOAD:
            raise RecoveryHttpError("media_read_bound")
        key = object_key(reference)
        if key not in self.expected:
            raise MediaObjectMissingError
        value = await asyncio.to_thread(self._read, key)
        self.reads += 1
        return value

    def _read(self, key: str) -> bytes:
        candidate = self.root
        if candidate.is_symlink() or not candidate.is_dir():
            raise RecoveryHttpError("media_root")
        for part in key.split("/"):
            if part in {"", ".", ".."}:
                raise RecoveryHttpError("media_path")
            candidate /= part
            if candidate.is_symlink():
                raise RecoveryHttpError("media_symlink")
        size, hashed = self.expected[key]
        descriptor = os.open(candidate, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size == size <= MAX_OBJECT_BYTES:
                raise RecoveryHttpError("media_size")
            data = stream.read(MAX_OBJECT_BYTES + 1)
        if len(data) != size or hashlib.sha256(data).hexdigest() != hashed:
            raise RecoveryHttpError("media_digest")
        return data

    async def upload_access(
        self, reference: MediaObjectRef, content_type: str, expires_at: datetime
    ) -> UploadAccess:
        del reference, content_type, expires_at
        raise RecoveryHttpError("media_write_forbidden")

    async def retain(self, reference: MediaObjectRef, data: bytes, content_type: str) -> None:
        del reference, data, content_type
        raise RecoveryHttpError("media_write_forbidden")

    async def remove_transport(self, reference: MediaObjectRef) -> None:
        del reference
        raise RecoveryHttpError("media_write_forbidden")


def expect(condition: bool, code: str) -> None:
    if not condition:
        raise RecoveryHttpError(code)


async def request(
    client: AsyncClient,
    method: str,
    path: str,
    expected: HTTPStatus,
    *,
    headers: dict[str, str] | None = None,
) -> Response:
    async with asyncio.timeout(HTTP_SECONDS):
        response = await client.request(method, path, headers=headers)
    expect(response.status_code == expected, "http_status")
    expect(len(response.content) <= MAX_OBJECT_BYTES, "http_body_bound")
    expect(bool(response.headers.get("x-request-id")), "http_correlation")
    return response


async def state(engine: AsyncEngine, protected_job: UUID) -> dict[str, str]:
    result: dict[str, str] = {}
    async with engine.connect() as connection, connection.begin():
        await connection.execute(text("SET TRANSACTION READ ONLY"))
        await connection.execute(text("SET LOCAL statement_timeout='2s'"))
        for table in TABLES:
            # Names are the fixed allowlist above, never operator input.
            queries = {
                "ai_jobs": (
                    "SELECT to_jsonb(t)::text FROM (SELECT * FROM public.ai_jobs LIMIT 33) t"
                ),
                "ai_intents": (
                    "SELECT to_jsonb(t)::text FROM (SELECT * FROM public.ai_intents LIMIT 33) t"
                ),
                "ai_attempts": (
                    "SELECT to_jsonb(t)::text FROM (SELECT * FROM public.ai_attempts LIMIT 33) t"
                ),
                "ai_executor_slot": (
                    "SELECT to_jsonb(t)::text FROM "
                    "(SELECT * FROM public.ai_executor_slot LIMIT 33) t"
                ),
            }
            raw: tuple[object, ...] = tuple(await connection.scalars(text(queries[table])))
            expect(all(isinstance(row, str) for row in raw), "state_shape")
            rows = tuple(sorted(row for row in raw if isinstance(row, str)))
            expect(len(rows) <= MAX_STATE_ROWS, "state_row_bound")
            result[table] = hashlib.sha256("\n".join(rows).encode()).hexdigest()
        protected = await connection.scalar(
            text("SELECT to_jsonb(t)::text FROM public.ai_jobs t WHERE id=:job"),
            {"job": protected_job},
        )
        expect(isinstance(protected, str), "protected_job_missing")
        if not isinstance(protected, str):
            raise RecoveryHttpError("protected_job_missing")
        result["protected_running_job"] = hashlib.sha256(protected.encode()).hexdigest()
    return result


async def audit_pairs(engine: AsyncEngine, operator: UUID) -> int:
    async with engine.connect() as connection:
        rows = tuple(
            (
                await connection.execute(
                    text(
                        "SELECT a.operator_id, count(e.id) FROM public.operator_audits a "
                        "LEFT JOIN public.product_events e ON e.operator_audit_id=a.id "
                        "AND e.kind='operator.inspected' GROUP BY a.id,a.operator_id LIMIT 33"
                    )
                )
            ).all()
        )
    expect(len(rows) <= MAX_STATE_ROWS, "audit_bound")
    expect(all(row[0] == operator and row[1] == 1 for row in rows), "audit_canonical_pair")
    return len(rows)


async def identity(client: AsyncClient, principal: Principal) -> IdentityResponse:
    response = await request(client, "GET", "/api/v1/me", HTTPStatus.OK)
    value = IdentityResponse.model_validate_json(response.content)
    expect(value.account_id == principal.account, "identity_account")
    expect(principal.credential.value not in response.text, "credential_response")
    return value


async def read_groups(
    case: RecoveryCase, engine: AsyncEngine, clients: dict[str, AsyncClient], media: RestoredMedia
) -> IdentityResponse:
    original = await state(engine, case.running_job)
    expect(await audit_pairs(engine, case.operator.account) == 0, "fixture_audit_not_empty")
    await request(clients["anonymous"], "GET", "/api/v1/me", HTTPStatus.UNAUTHORIZED)
    for name in ("malformed", "expired", "revoked", "deleted"):
        await request(clients[name], "GET", "/api/v1/me", HTTPStatus.UNAUTHORIZED)
    me = await identity(clients["owner"], case.owner)
    expect(me.membership_status == "verified", "identity_membership")
    path = "/api/v1/operator/accounts/" + str(case.deleted.account)
    await request(clients["owner"], "GET", path, HTTPStatus.FORBIDDEN)
    await request(clients["revoked_operator"], "GET", path, HTTPStatus.FORBIDDEN)
    retained = await request(clients["operator"], "GET", path, HTTPStatus.OK)
    detail = OperatorAccountDetailResponse.model_validate_json(retained.content)
    expect(detail.account.account_id == case.deleted.account, "retained_account")
    expect(detail.account.deleted_at is not None, "retained_deleted_account")
    expect(retained.headers.get("cache-control") == "no-store", "operator_private_headers")
    photo = "/api/v1/media/" + str(case.photo) + "/display"
    before = media.reads
    await request(clients["other"], "GET", photo, HTTPStatus.NOT_FOUND)
    expect(media.reads == before, "unauthorized_media_read")
    display = await request(clients["owner"], "GET", photo, HTTPStatus.OK)
    expect(len(display.content) == case.display_size, "display_size")
    expect(hashlib.sha256(display.content).hexdigest() == case.display_sha256, "display_sha256")
    expect(display.headers.get("content-type") == "image/jpeg", "display_type")
    expect("no-store" in display.headers.get("cache-control", ""), "display_private")
    operator_photo = (
        "/api/v1/operator/accounts/"
        + str(case.owner.account)
        + "/photo-uploads/"
        + str(case.photo)
        + "/attempts/"
        + str(case.attempt)
        + "/display"
    )
    attachment = await request(clients["operator"], "GET", operator_photo, HTTPStatus.OK)
    expect(attachment.content == display.content, "operator_display_bytes")
    expect(
        attachment.headers.get("content-disposition", "").startswith("attachment;"), "attachment"
    )
    for job, status in ((case.queued_job, "queued"), (case.running_job, "running")):
        job_path = "/api/v1/ai/jobs/" + str(job)
        await request(clients["other"], "GET", job_path, HTTPStatus.NOT_FOUND)
        response = await request(clients["owner"], "GET", job_path, HTTPStatus.OK)
        value = JobResponse.model_validate_json(response.content)
        expect(value.id == job and value.state.value == status, "retained_queue_state")
    operator_job = (
        "/api/v1/operator/accounts/" + str(case.owner.account) + "/ai-jobs/" + str(case.running_job)
    )
    await request(clients["operator"], "GET", operator_job, HTTPStatus.OK)
    expect(await state(engine, case.running_job) == original, "http_reads_mutated_queue")
    expect(
        await audit_pairs(engine, case.operator.account) == EXPECTED_AUDITS, "operator_audit_count"
    )
    return me


async def write_groups(
    case: RecoveryCase, engine: AsyncEngine, client: AsyncClient, me: IdentityResponse
) -> None:
    path = "/api/v1/ai/jobs/" + str(case.queued_job) + "/cancel"
    before = await state(engine, case.running_job)
    await request(client, "POST", path, HTTPStatus.FORBIDDEN, headers={"Origin": ORIGIN})
    await request(
        client,
        "POST",
        path,
        HTTPStatus.FORBIDDEN,
        headers={
            "Origin": "https://foreign.invalid",
            "X-CSRF-Token": me.csrf_token,
        },
    )
    expect(await state(engine, case.running_job) == before, "rejected_write_changed_queue")
    headers = {"Origin": ORIGIN, "X-CSRF-Token": me.csrf_token}
    after_first: dict[str, str] | None = None
    for _ in range(2):
        response = await request(client, "POST", path, HTTPStatus.OK, headers=headers)
        value = JobResponse.model_validate_json(response.content)
        expect(value.state.value == "cancelled", "cancel_state")
        current = await state(engine, case.running_job)
        if after_first is None:
            after_first = current
        else:
            expect(current == after_first, "repeated_cancel_changed_queue")
    after = await state(engine, case.running_job)
    expect(after["ai_jobs"] != before["ai_jobs"], "cancel_not_committed")
    expect(
        all(after[t] == before[t] for t in before if t != "ai_jobs"), "cancel_changed_lease_intent"
    )
    # Running job remains owned and unchanged while only the queued job is cancelled.
    running = await request(
        client, "GET", "/api/v1/ai/jobs/" + str(case.running_job), HTTPStatus.OK
    )
    expect(
        JobResponse.model_validate_json(running.content).state.value == "running", "running_lease"
    )
    await request(
        client, "POST", "/api/v1/auth/logout", HTTPStatus.FORBIDDEN, headers={"Origin": ORIGIN}
    )
    await identity(client, case.owner)
    await request(client, "POST", "/api/v1/auth/logout", HTTPStatus.NO_CONTENT, headers=headers)
    expect(SESSION_COOKIE not in client.cookies, "logout_cookie")
    client.cookies.set(
        SESSION_COOKIE, case.owner.credential.value, domain="recovery.invalid", path="/"
    )
    await request(client, "GET", "/api/v1/me", HTTPStatus.UNAUTHORIZED)
