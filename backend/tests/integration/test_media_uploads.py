import asyncio
from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import StudentActionDeniedError
from studymate.application.media.uploads import (
    MAX_PENDING_UPLOADS,
    UPLOADS_PER_HOUR,
    PhotoUploadCommand,
    PhotoUploadRateLimitedError,
    PhotoUploadUnavailableError,
    PhotoVersionConflictError,
    UploadAction,
)
from studymate.domain.media import PhotoUploadState
from studymate.infrastructure.persistence.media_models import (
    MediaIntentRecord,
    PhotoRecord,
    PhotoRevisionRecord,
    PhotoUploadRecord,
    PhotoUploadRevisionRecord,
)
from studymate.infrastructure.persistence.media_uploads import SqlMediaUnitOfWork
from studymate.infrastructure.persistence.photo_attempt_models import PhotoAttemptRecord
from tests.integration.media_fixture import command, services
from tests.integration.student_actor import Actor, actor

pytestmark = pytest.mark.integration


def action(owner: Actor, upload_id: UUID, value: UploadAction) -> PhotoUploadCommand:
    return PhotoUploadCommand(owner.credential, upload_id, value, IntentKey(str(uuid4())))


async def test_photo_upload_resume_original_intents_and_cancel_finalization_race(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    start, change, read = services(identity_engine)
    submitted = command(owner)
    first, duplicate = await asyncio.gather(start(submitted), start(submitted))
    assert first == duplicate
    assert await read(owner.credential, first.id) == first
    finalize = action(owner, first.id, UploadAction.FINALIZE)
    cancel = action(owner, first.id, UploadAction.CANCEL)
    await asyncio.gather(change(finalize), change(cancel))
    cancelled = await read(owner.credential, first.id)
    assert cancelled.state == PhotoUploadState.CANCELLED
    assert await start(submitted) == first
    assert (await change(cancel)).state == PhotoUploadState.CANCELLED
    assert (await change(finalize)).state in {PhotoUploadState.QUEUED, PhotoUploadState.CANCELLED}
    assert await read(owner.credential, first.id) == cancelled
    with pytest.raises(IdempotencyConflictError):
        await start(replace(submitted, source=replace(submitted.source, size=11)))
    with pytest.raises(IdempotencyConflictError):
        await change(replace(cancel, action=UploadAction.FINALIZE))
    async with async_sessionmaker(identity_engine)() as session:
        assert (
            await session.scalars(select(func.count()).select_from(PhotoUploadRecord))
        ).one() == 1
        assert (
            await session.scalars(select(func.count()).select_from(MediaIntentRecord))
        ).one() == len((submitted, finalize, cancel))


async def test_photo_upload_limits_active_slots_and_replays_do_not_spend_capacity(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    start, change, _ = services(identity_engine)
    submitted = command(owner)
    first = await start(submitted)
    for _ in range(MAX_PENDING_UPLOADS - 1):
        await start(command(owner))
    assert await start(submitted) == first
    with pytest.raises(PhotoUploadRateLimitedError) as limited:
        await start(command(owner))
    assert limited.value.retry_at <= first.processing_expires_at
    await change(action(owner, first.id, UploadAction.CANCEL))
    assert (await start(command(owner))).state == PhotoUploadState.UPLOADING


async def test_hourly_upload_limit_survives_cancelled_attempts(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    start, change, _ = services(identity_engine)
    for _ in range(UPLOADS_PER_HOUR):
        current = await start(command(owner))
        await change(action(owner, current.id, UploadAction.CANCEL))
    with pytest.raises(PhotoUploadRateLimitedError):
        await start(command(owner))
    async with async_sessionmaker(identity_engine)() as session:
        assert (
            await session.scalars(select(func.count()).select_from(PhotoUploadRecord))
        ).one() == UPLOADS_PER_HOUR


async def test_expired_upload_is_durable_and_releases_pending_slot(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    start, _, read = services(identity_engine)
    original = await start(command(owner))
    async with async_sessionmaker(identity_engine).begin() as session:
        await session.execute(
            update(PhotoUploadRecord).values(
                created_at=func.clock_timestamp() - timedelta(minutes=20),
                upload_expires_at=func.clock_timestamp() - timedelta(minutes=5),
                processing_expires_at=func.clock_timestamp() + timedelta(minutes=40),
            )
        )
        await session.execute(
            update(PhotoUploadRevisionRecord).values(
                updated_at=func.clock_timestamp() - timedelta(minutes=20)
            )
        )
    expired = await read(owner.credential, original.id)
    assert expired.state == PhotoUploadState.EXPIRED
    assert expired.version == original.version + 1
    assert await read(owner.credential, original.id) == expired
    for _ in range(MAX_PENDING_UPLOADS):
        await start(command(owner))
    async with async_sessionmaker(identity_engine)() as session:
        old = await session.get(PhotoUploadRevisionRecord, (original.id, original.version))
        assert old is not None
        assert old.state == PhotoUploadState.UPLOADING


async def test_media_is_owner_scoped_and_verification_is_required(
    identity_engine: AsyncEngine,
) -> None:
    owner, other = await actor(identity_engine), await actor(identity_engine)
    start, change, read = services(identity_engine)
    current = await start(command(owner))
    with pytest.raises(PhotoUploadUnavailableError):
        await read(other.credential, current.id)
    with pytest.raises(PhotoUploadUnavailableError):
        await change(action(other, current.id, UploadAction.CANCEL))
    unverified = await actor(identity_engine, verified=False)
    with pytest.raises(StudentActionDeniedError):
        await start(command(unverified))
    with pytest.raises(StudentActionDeniedError):
        await read(unverified.credential, current.id)
    with pytest.raises(PhotoVersionConflictError) as stale:
        await start(command(owner, version=1))
    assert stale.value.current_version == 0


async def test_current_photo_must_reference_owned_ready_upload_and_history_is_retained(
    identity_engine: AsyncEngine,
) -> None:
    owner, other = await actor(identity_engine), await actor(identity_engine)
    start, _, _ = services(identity_engine)
    current = await start(command(owner))
    with pytest.raises(IntegrityError):
        async with async_sessionmaker(identity_engine).begin() as session:
            session.add(
                PhotoRevisionRecord(
                    account_id=owner.id,
                    version=1,
                    upload_id=current.id,
                    upload_version=current.version,
                    upload_state="ready",
                    saved_at=current.created_at,
                )
            )
    attempt_id = uuid4()
    async with async_sessionmaker(identity_engine).begin() as session:
        session.add(
            PhotoAttemptRecord(
                id=attempt_id,
                upload_id=current.id,
                number=1,
                started_at=current.created_at,
                lease_until=current.created_at + timedelta(minutes=2),
                finished_at=current.created_at,
                outcome="ready",
                display_width=1,
                display_height=1,
                display_size=1,
                display_digest=bytes(range(32)),
            )
        )
    async with SqlMediaUnitOfWork(
        async_sessionmaker(identity_engine, expire_on_commit=False)
    ).transaction() as transaction:
        # Controlled storage-independent DB fixture, not a claim of real photo processing.
        queued = current.queue(current.created_at)
        processing = queued.processing(attempt_id, current.created_at)
        assert processing.attempt_id is not None
        ready = processing.ready(processing.attempt_id, current.created_at)
        for value in (queued, processing, ready):
            await transaction.save_upload(value)
    with pytest.raises(IntegrityError):
        async with async_sessionmaker(identity_engine).begin() as session:
            session.add(
                PhotoRevisionRecord(
                    account_id=other.id,
                    version=1,
                    upload_id=ready.id,
                    upload_version=ready.version,
                    upload_state="ready",
                    saved_at=ready.created_at,
                )
            )
    async with async_sessionmaker(identity_engine).begin() as session:
        session.add(
            PhotoRevisionRecord(
                account_id=owner.id,
                version=1,
                upload_id=ready.id,
                upload_version=ready.version,
                upload_state="ready",
                saved_at=ready.created_at,
            )
        )
        await session.flush()
        session.add(PhotoRecord(account_id=owner.id, current_version=1))
    async with SqlMediaUnitOfWork(async_sessionmaker(identity_engine)).transaction() as transaction:
        photo = await transaction.current_photo(owner.id)
        assert photo is not None
        assert photo.upload_id == current.id
        assert await transaction.current_photo(other.id) is None
        assert await transaction.upload(owner.id, current.id, ready.version + 1) is None
    with pytest.raises(PhotoVersionConflictError) as stale:
        await start(command(owner))
    assert stale.value.current_version == 1
    with pytest.raises(IntegrityError):
        async with async_sessionmaker(identity_engine).begin() as session:
            await session.execute(
                delete(PhotoUploadRevisionRecord).where(
                    PhotoUploadRevisionRecord.upload_id == current.id
                )
            )
