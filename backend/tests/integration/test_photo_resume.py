import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.media.resume import RECENT_TERMINAL_UPLOADS, ReadOwnPhotoResume
from studymate.application.media.uploads import (
    MAX_PENDING_UPLOADS,
    PhotoUploadCommand,
    UploadAction,
)
from studymate.domain.media import PhotoUploadState
from studymate.infrastructure.media.images import BoundedImageProcessor
from studymate.infrastructure.persistence.discovery_freshness_models import DiscoveryExposureRecord
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.media_models import PhotoUploadRecord
from studymate.infrastructure.persistence.media_resume import SqlPhotoResumeUnitOfWork
from studymate.infrastructure.persistence.photo_worker import SqlPhotoWorkerTransaction
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from studymate.presentation.media import OwnPhotoResumeResponse
from tests.image_fixture import encoded
from tests.integration.http_identity import BrowserHarness, login, verified, write_headers
from tests.integration.media_fixture import command, services, worker
from tests.integration.onboarding_fixture import ready_setup
from tests.integration.profile_lifecycle_fixture import activated
from tests.integration.student_actor import actor
from tests.integration.test_media_http import payload

pytestmark = pytest.mark.integration


def reader(engine: AsyncEngine) -> ReadOwnPhotoResume:
    return ReadOwnPhotoResume(
        SqlPhotoResumeUnitOfWork(async_sessionmaker(engine, expire_on_commit=False)),
        Sha256SessionHasher(),
    )


async def test_http_reload_recovers_three_unknown_uploads_and_committed_ready(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    await verified(browser, identity_engine)
    client, data = browser.client, encoded()
    for _ in range(MAX_PENDING_UPLOADS):
        # Deliberately retain no upload ID from the successful Start responses.
        response = await client.post(
            "/api/v1/media/uploads", json=payload(data), headers=await write_headers(client)
        )
        assert response.status_code == HTTPStatus.ACCEPTED
    foreign = await actor(identity_engine)
    start, _, _ = services(identity_engine)
    foreign_upload = await start(command(foreign))
    recovered = await client.get(f"/api/v1/media/uploads?account_id={foreign.id}")
    assert recovered.status_code == HTTPStatus.OK
    assert recovered.headers["cache-control"] == "no-store"
    snapshot = OwnPhotoResumeResponse.model_validate(recovered.json())
    assert snapshot.photo is None
    assert hashlib.sha256(data).hexdigest() not in repr(snapshot)
    assert len(snapshot.uploads) == MAX_PENDING_UPLOADS
    assert foreign_upload.id not in {item.upload.id for item in snapshot.uploads}
    assert all(item.source_sha256 == hashlib.sha256(data).hexdigest() for item in snapshot.uploads)
    assert all(item.upload.state == PhotoUploadState.UPLOADING for item in snapshot.uploads)
    assert all(set(item) == {"upload", "source_sha256"} for item in recovered.json()["uploads"])
    upload_id = snapshot.uploads[0].upload.id
    final = await client.post(
        f"/api/v1/media/uploads/{upload_id}/finalize", headers=await write_headers(client)
    )
    assert final.status_code == HTTPStatus.ACCEPTED
    queued = OwnPhotoResumeResponse.model_validate(
        (await client.get("/api/v1/media/uploads")).json()
    )
    assert (
        next(item.upload for item in queued.uploads if item.upload.id == upload_id).state
        == PhotoUploadState.QUEUED
    )
    browser.storage.data = data
    processor = BoundedImageProcessor()
    try:
        await worker(identity_engine, browser.storage, processor)()
    finally:
        await processor.close()
    ready = OwnPhotoResumeResponse.model_validate(
        (await client.get("/api/v1/media/uploads")).json()
    )
    assert ready.photo is not None
    assert ready.photo.upload_id == upload_id
    assert (
        next(item.upload for item in ready.uploads if item.upload.id == upload_id).state
        == PhotoUploadState.READY
    )
    assert not browser.storage.accesses  # Resume never creates signed storage tickets.


async def test_resume_bounds_history_without_losing_pending_or_current_photo(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    await ready_setup(identity_engine, owner.credential)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    first = await reader(identity_engine)(owner.credential)
    assert first.photo is not None
    published_id = first.photo.upload_id
    async with sessions.begin() as session:
        await session.execute(
            update(PhotoUploadRecord).values(created_at=datetime.now(UTC) - timedelta(hours=2))
        )
    start, change, _ = services(identity_engine)
    for _ in range(RECENT_TERMINAL_UPLOADS):
        pending = await start(command(owner, version=1))
        await change(
            PhotoUploadCommand(
                owner.credential, pending.id, UploadAction.CANCEL, IntentKey(str(uuid4()))
            )
        )
    async with sessions.begin() as session:
        await session.execute(
            update(PhotoUploadRecord).values(created_at=datetime.now(UTC) - timedelta(hours=2))
        )
    pending_ids = {(await start(command(owner, version=1))).id for _ in range(MAX_PENDING_UPLOADS)}
    resumed = await reader(identity_engine)(owner.credential)
    assert resumed.photo is not None
    assert resumed.photo.upload_id == published_id
    assert len(resumed.uploads) == RECENT_TERMINAL_UPLOADS + MAX_PENDING_UPLOADS + 1
    assert {item.id for item in resumed.uploads if item.pending} == pending_ids
    assert published_id in {item.id for item in resumed.uploads}
    assert len({item.id for item in resumed.uploads}) == len(resumed.uploads)


async def test_resume_expires_actual_revision_without_warming_discovery_activity(
    identity_engine: AsyncEngine,
) -> None:
    owner = await activated(identity_engine)
    start, _, _ = services(identity_engine)
    pending = await start(command(owner, version=1))
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        source = await session.get(DiscoveryExposureRecord, owner.id)
        assert source is not None
        activity = source.last_activity_at
        await session.execute(
            update(PhotoUploadRecord)
            .where(PhotoUploadRecord.id == pending.id)
            .values(
                created_at=datetime.now(UTC) - timedelta(minutes=20),
                upload_expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
    snapshot = await reader(identity_engine)(owner.credential)
    expired = next(upload for upload in snapshot.uploads if upload.id == pending.id)
    assert expired.state == PhotoUploadState.EXPIRED
    assert expired.version == pending.version + 1
    async with sessions() as session:
        source = await session.get(DiscoveryExposureRecord, owner.id)
        assert source is not None
        assert source.last_activity_at == activity
        stored = await session.get(PhotoUploadRecord, pending.id)
        assert stored is not None
        assert stored.current_version == expired.version


@pytest.mark.parametrize("state", ["unauthenticated", "unverified", "banned", "deleted"])
async def test_http_photo_resume_uses_live_owner_permissions(
    browser: BrowserHarness, identity_engine: AsyncEngine, state: str
) -> None:
    if state == "unverified":
        await login(browser.client)
    elif state != "unauthenticated":
        owner_id = await verified(browser, identity_engine)
        column = AccountRecord.banned_at if state == "banned" else AccountRecord.deleted_at
        async with async_sessionmaker(identity_engine).begin() as session:
            await session.execute(
                update(AccountRecord)
                .where(AccountRecord.id == owner_id)
                .values({column: datetime.now(UTC)})
            )
    response = await browser.client.get("/api/v1/media/uploads")
    expected = (
        HTTPStatus.UNAUTHORIZED if state in {"unauthenticated", "deleted"} else HTTPStatus.FORBIDDEN
    )
    assert response.status_code == expected
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-request-id"] == response.json()["request_id"]


async def test_resume_waits_for_claim_and_returns_current_worker_revision(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    start, change, _ = services(identity_engine)
    upload = await start(command(owner))
    queued = await change(
        PhotoUploadCommand(
            owner.credential, upload.id, UploadAction.FINALIZE, IntentKey(str(uuid4()))
        )
    )
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with asyncio.TaskGroup() as tasks:
        async with sessions.begin() as worker_session:
            await worker_session.execute(
                select(PhotoUploadRecord.id)
                .where(PhotoUploadRecord.id == upload.id)
                .with_for_update()
            )
            blocker: object = await worker_session.scalar(select(func.pg_backend_pid()))
            assert isinstance(blocker, int)
            pending = tasks.create_task(reader(identity_engine)(owner.credential))
            async with asyncio.timeout(3):
                while True:
                    async with sessions() as observer:
                        waiting = await observer.scalar(
                            text(
                                "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                                "WHERE :blocker = ANY(pg_blocking_pids(pid)))"
                            ),
                            {"blocker": blocker},
                        )
                    if waiting:
                        break
                    await asyncio.sleep(0.01)
            transaction = SqlPhotoWorkerTransaction(worker_session)
            now = await transaction.now()
            claimed = await transaction.claim(now, now + timedelta(minutes=2))
            assert claimed is not None
            assert claimed.upload.id == upload.id
        resumed = await asyncio.wait_for(pending, timeout=3)
    current = next(item for item in resumed.uploads if item.id == upload.id)
    assert current.state == PhotoUploadState.PROCESSING
    assert current.version == queued.version + 1
