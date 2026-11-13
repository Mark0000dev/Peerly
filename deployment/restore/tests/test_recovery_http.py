import asyncio
import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path
from uuid import uuid4

import httpx2
import pytest
from deployment.restore import recovery_http
from deployment.restore.recovery_http import (
    MAX_READS,
    Principal,
    RecoveryCase,
    RecoveryHttpError,
    RestoredMedia,
)
from deployment.restore.recovery_http_app import DeniedProviderHttp
from httpx2 import AsyncClient, MockTransport, Request, Response
from sqlalchemy.ext.asyncio import create_async_engine

from studymate.application.identity.sessions import SessionCredential
from studymate.application.media.storage import MediaObjectMissingError
from studymate.domain.media import MediaObjectKind, MediaObjectRef
from studymate.infrastructure.media.s3 import object_key

PRIVATE = "SYNTHETIC_PRIVATE_BODY_MUST_NOT_ESCAPE"
TARGET = "peerly_restore_" + "a" * 32 + "_test"


def fixture() -> RecoveryCase:
    principals = tuple(
        Principal(uuid4(), SessionCredential(uuid4().hex + uuid4().hex[:11])) for _ in range(7)
    )
    return RecoveryCase(
        synthetic_not_real_backup=True,
        source="peerly_http_source_" + "b" * 32 + "_test",
        target=TARGET,
        owner=principals[0],
        other=principals[1],
        operator=principals[2],
        expired=principals[3],
        revoked=principals[4],
        deleted=principals[5],
        revoked_operator=principals[6],
        photo=uuid4(),
        attempt=uuid4(),
        queued_job=uuid4(),
        running_job=uuid4(),
        display_sha256="c" * 64,
        display_size=16,
    )


def test_fixture_repr_never_contains_session_secrets() -> None:
    case = fixture()
    assert case.owner.credential.value not in repr(case)
    assert case.operator.credential.value not in repr(case)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://127.0.0.1/shared_test",
        "postgresql+asyncpg://remote.invalid/" + TARGET,
        "postgresql+asyncpg://127.0.0.1/" + TARGET + "?host=remote.invalid",
        "postgresql+asyncpg://synthetic:password@127.0.0.1/" + TARGET,
    ],
)
async def test_unsafe_database_rejected_without_connection(url: str) -> None:
    engine = create_async_engine(url)
    try:
        with pytest.raises(RecoveryHttpError, match="synthetic_owned_database_required"):
            fixture().guard(engine)
    finally:
        await engine.dispose()


async def test_synthetic_and_distinct_authority_guards() -> None:
    engine = create_async_engine("postgresql+asyncpg://127.0.0.1/" + TARGET)
    case = fixture()
    try:
        case.guard(engine)
        with pytest.raises(RecoveryHttpError, match="synthetic_owned_database_required"):
            replace(case, synthetic_not_real_backup=False).guard(engine)
        with pytest.raises(RecoveryHttpError, match="fixture_authority_collision"):
            replace(case, operator=case.owner).guard(engine)
        with pytest.raises(RecoveryHttpError, match="fixture_identity_collision"):
            replace(case, revoked=case.owner).guard(engine)
    finally:
        await engine.dispose()


def media(root: Path) -> tuple[RestoredMedia, MediaObjectRef, Path]:
    reference = MediaObjectRef(uuid4(), MediaObjectKind.DISPLAY, uuid4())
    key = object_key(reference)
    candidate = root / key
    candidate.parent.mkdir(parents=True)
    data = b"synthetic_media_only"
    candidate.write_bytes(data)
    return (
        RestoredMedia(root, {key: (len(data), hashlib.sha256(data).hexdigest())}),
        reference,
        candidate,
    )


async def test_restored_media_reads_exact_hash_and_bounds_access(tmp_path: Path) -> None:
    storage, reference, candidate = media(tmp_path)
    for _ in range(MAX_READS):
        assert await storage.read(reference) == candidate.read_bytes()
    with pytest.raises(RecoveryHttpError, match="media_read_bound"):
        await storage.read(reference)


async def test_missing_media_never_guesses_current_object(tmp_path: Path) -> None:
    storage, _, _ = media(tmp_path)
    with pytest.raises(MediaObjectMissingError):
        await storage.read(MediaObjectRef(uuid4(), MediaObjectKind.DISPLAY, uuid4()))
    assert storage.reads == 0


async def test_media_tamper_and_symlink_reject_without_success_receipt(tmp_path: Path) -> None:
    storage, reference, candidate = media(tmp_path)
    original = candidate.read_bytes()
    candidate.write_bytes(b"x" * len(original))
    with pytest.raises(RecoveryHttpError, match="media_digest"):
        await storage.read(reference)
    candidate.unlink()
    outside = tmp_path / "outside"
    outside.write_bytes(original)
    candidate.symlink_to(outside)
    with pytest.raises(RecoveryHttpError, match="media_symlink"):
        await storage.read(reference)
    assert storage.reads == 0


async def test_all_media_writes_are_rejected(tmp_path: Path) -> None:
    storage, reference, candidate = media(tmp_path)
    before = candidate.read_bytes()
    with pytest.raises(RecoveryHttpError, match="media_write_forbidden"):
        await storage.upload_access(reference, "image/jpeg", datetime.now(UTC))
    with pytest.raises(RecoveryHttpError, match="media_write_forbidden"):
        await storage.retain(reference, b"different", "image/jpeg")
    with pytest.raises(RecoveryHttpError, match="media_write_forbidden"):
        await storage.remove_transport(reference)
    assert candidate.read_bytes() == before


def test_provider_trap_never_echoes_url_or_secrets() -> None:
    denied = DeniedProviderHttp()
    with pytest.raises(RecoveryHttpError, match="external_provider_attempt") as captured:
        denied.reject(httpx2.Request("POST", "https://provider.invalid/" + PRIVATE))
    assert denied.attempts == 1
    assert PRIVATE not in str(captured.value)


async def test_unexpected_http_body_never_enters_error() -> None:
    def boundary(request: Request) -> Response:
        return Response(500, text=PRIVATE, request=request)

    async with AsyncClient(
        transport=MockTransport(boundary), base_url="https://recovery.invalid"
    ) as client:
        with pytest.raises(RecoveryHttpError, match="http_status") as captured:
            await recovery_http.request(client, "GET", "/api/v1/me", HTTPStatus.OK)
    assert PRIVATE not in str(captured.value)


async def test_http_deadline_is_real_for_inprocess_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def blocked(request: Request) -> Response:
        del request
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    monkeypatch.setattr(recovery_http, "HTTP_SECONDS", 0.01)
    async with AsyncClient(
        transport=MockTransport(blocked), base_url="https://recovery.invalid"
    ) as client:
        with pytest.raises(TimeoutError):
            await recovery_http.request(client, "GET", "/api/v1/me", HTTPStatus.OK)
