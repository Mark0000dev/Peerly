import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.media.uploads import PhotoUploadCommand, UploadAction
from studymate.application.media.worker import (
    MAX_PHOTO_ATTEMPTS,
    PhotoImageInfo,
    PhotoLease,
    PhotoProcessingStep,
)
from studymate.domain.media import (
    MediaObjectKind,
    MediaObjectRef,
    PhotoFailure,
    PhotoUploadState,
)
from studymate.infrastructure.media.images import BoundedImageProcessor
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
)
from studymate.infrastructure.persistence.media_models import PhotoUploadRecord
from studymate.infrastructure.persistence.media_uploads import SqlMediaUnitOfWork
from studymate.infrastructure.persistence.photo_attempt_models import PhotoAttemptRecord
from studymate.infrastructure.persistence.photo_worker import SqlPhotoWorkerUnitOfWork
from tests.image_fixture import encoded
from tests.integration.media_fixture import Storage, queued, services, worker
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration


async def test_photo_worker_publishes_only_after_verified_private_copies(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    data = encoded()
    upload = await queued(identity_engine, owner, data)
    storage = Storage(data)
    processor = BoundedImageProcessor()
    try:
        process = worker(identity_engine, storage, processor)
        assert await process() == PhotoProcessingStep.READY
        assert await process() == PhotoProcessingStep.IDLE
    finally:
        await processor.close()
    _, _, read = services(identity_engine)
    ready = await read(owner.credential, upload.id)
    assert ready.state == PhotoUploadState.READY
    assert ready.attempt_id is not None
    assert (
        storage.retained[MediaObjectRef(upload.id, MediaObjectKind.ORIGINAL, ready.attempt_id)]
        == data
    )
    assert storage.retained[
        MediaObjectRef(upload.id, MediaObjectKind.DISPLAY, ready.attempt_id)
    ].startswith(b"\xff\xd8\xff")
    async with SqlMediaUnitOfWork(async_sessionmaker(identity_engine)).transaction() as transaction:
        photo = await transaction.current_photo(owner.id)
        assert photo is not None
        assert photo.upload_id == upload.id
    async with async_sessionmaker(identity_engine)() as session:
        attempt = (await session.scalars(select(PhotoAttemptRecord))).one()
        assert attempt.outcome == "ready"
        assert attempt.display_digest is not None
        assert attempt.finished_at is not None


async def test_cancellation_during_storage_io_wins_and_late_outputs_stay_private(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    data = encoded()
    upload = await queued(identity_engine, owner, data)
    storage = Storage(data, pause=True)
    processor = BoundedImageProcessor()
    task = asyncio.create_task(worker(identity_engine, storage, processor)())
    try:
        await asyncio.wait_for(storage.started.wait(), timeout=2)
        _, change, read = services(identity_engine)
        cancelled = await asyncio.wait_for(
            change(
                PhotoUploadCommand(
                    owner.credential, upload.id, UploadAction.CANCEL, IntentKey(str(uuid4()))
                )
            ),
            timeout=2,
        )
        assert cancelled.state == PhotoUploadState.CANCELLED
        storage.release.set()
        assert await task == PhotoProcessingStep.STALE
        assert await read(owner.credential, upload.id) == cancelled
        assert storage.retained
    finally:
        storage.release.set()
        await task
        await processor.close()
    async with SqlMediaUnitOfWork(async_sessionmaker(identity_engine)).transaction() as transaction:
        assert await transaction.current_photo(owner.id) is None


async def test_two_uploads_from_same_photo_version_cannot_both_replace_it(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    data = encoded()
    first, second = (
        await queued(identity_engine, owner, data),
        await queued(identity_engine, owner, data),
    )
    storage = Storage(data)
    processor = BoundedImageProcessor()
    try:
        process = worker(identity_engine, storage, processor)
        assert await process() == PhotoProcessingStep.READY
        assert await process() == PhotoProcessingStep.REJECTED
    finally:
        await processor.close()
    _, _, read = services(identity_engine)
    ready = await read(owner.credential, first.id)
    rejected = await read(owner.credential, second.id)
    assert ready.state == PhotoUploadState.READY
    assert rejected.failure == PhotoFailure.PHOTO_CHANGED
    async with SqlMediaUnitOfWork(async_sessionmaker(identity_engine)).transaction() as transaction:
        current = await transaction.current_photo(owner.id)
        assert current is not None
        assert current.upload_id == first.id
        assert current.version == 1


@pytest.mark.parametrize("change", ["size", "digest", "invalid"])
async def test_worker_rejects_changed_or_invalid_source_without_publication(
    identity_engine: AsyncEngine, change: str
) -> None:
    owner = await actor(identity_engine)
    data = b"invalid image" if change == "invalid" else encoded()
    upload = await queued(identity_engine, owner, data)
    actual = (
        data + b"changed"
        if change == "size"
        else bytes([data[0] ^ 1]) + data[1:]
        if change == "digest"
        else data
    )
    storage = Storage(actual)
    processor = BoundedImageProcessor()
    try:
        assert await worker(identity_engine, storage, processor)() == PhotoProcessingStep.REJECTED
    finally:
        await processor.close()
    _, _, read = services(identity_engine)
    result = await read(owner.credential, upload.id)
    assert result.failure == (
        PhotoFailure.UNSUPPORTED_FORMAT if change == "invalid" else PhotoFailure.CONTENT_CHANGED
    )
    assert storage.retained == {}


async def test_worker_retries_are_persistent_bounded_and_do_not_hot_loop(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    data = encoded()
    upload = await queued(identity_engine, owner, data)
    storage = Storage(data, unavailable=True)
    processor = BoundedImageProcessor()
    try:
        process = worker(identity_engine, storage, processor)
        assert await process() == PhotoProcessingStep.RETRY
        assert await process() == PhotoProcessingStep.IDLE
        async with async_sessionmaker(identity_engine).begin() as session:
            await session.execute(
                update(PhotoAttemptRecord).values(next_attempt_at=func.clock_timestamp())
            )
        assert await process() == PhotoProcessingStep.RETRY
        async with async_sessionmaker(identity_engine).begin() as session:
            await session.execute(
                update(PhotoAttemptRecord)
                .where(PhotoAttemptRecord.outcome == "retry")
                .values(next_attempt_at=func.clock_timestamp())
            )
        assert await process() == PhotoProcessingStep.REJECTED
        assert await process() == PhotoProcessingStep.IDLE
    finally:
        await processor.close()
    _, _, read = services(identity_engine)
    assert (await read(owner.credential, upload.id)).failure == PhotoFailure.STORAGE_UNAVAILABLE
    async with async_sessionmaker(identity_engine)() as session:
        attempts = (
            await session.scalars(select(PhotoAttemptRecord).order_by(PhotoAttemptRecord.number))
        ).all()
        assert [item.outcome for item in attempts] == ["retry", "retry", "rejected"]


async def test_worker_rechecks_lifecycle_after_io_without_discarding_history(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    data = encoded()
    upload = await queued(identity_engine, owner, data)
    storage = Storage(data, pause=True)
    processor = BoundedImageProcessor()
    task = asyncio.create_task(worker(identity_engine, storage, processor)())
    try:
        await asyncio.wait_for(storage.started.wait(), timeout=2)
        async with async_sessionmaker(identity_engine).begin() as session:
            await session.execute(
                update(AccountRecord)
                .where(AccountRecord.id == owner.id)
                .values(deleted_at=func.clock_timestamp())
            )
        storage.release.set()
        assert await task == PhotoProcessingStep.REJECTED
    finally:
        storage.release.set()
        await task
        await processor.close()
    async with SqlMediaUnitOfWork(async_sessionmaker(identity_engine)).transaction() as transaction:
        assert await transaction.current_photo(owner.id) is None
        retained = await transaction.upload(owner.id, upload.id)
        assert retained is not None
        assert retained.failure == PhotoFailure.ACCOUNT_UNAVAILABLE
    assert storage.retained


async def test_interrupted_worker_reclaims_generation_and_old_completion_cannot_publish(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    data = encoded()
    upload = await queued(identity_engine, owner, data)
    storage = Storage(data, pause=True)
    processor = BoundedImageProcessor()
    process = worker(identity_engine, storage, processor)
    task = asyncio.create_task(process())
    try:
        await asyncio.wait_for(storage.started.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        async with SqlMediaUnitOfWork(
            async_sessionmaker(identity_engine)
        ).transaction() as transaction:
            interrupted = await transaction.upload(owner.id, upload.id)
        assert interrupted is not None
        assert interrupted.attempt_id is not None
        lease = PhotoLease(interrupted, interrupted.attempt_id, 1)
        async with async_sessionmaker(identity_engine).begin() as session:
            await session.execute(
                update(PhotoAttemptRecord).values(
                    started_at=func.clock_timestamp() - timedelta(minutes=2),
                    lease_until=func.clock_timestamp() - timedelta(minutes=1),
                )
            )
        storage.pause = False
        assert await process() == PhotoProcessingStep.READY
        async with SqlPhotoWorkerUnitOfWork(
            async_sessionmaker(identity_engine)
        ).transaction() as transaction:
            assert (
                await transaction.complete(
                    lease, PhotoImageInfo(1, 1, 1, bytes(range(32))), await transaction.now()
                )
                == PhotoProcessingStep.STALE
            )
        async with async_sessionmaker(identity_engine)() as session:
            attempts = (
                await session.scalars(
                    select(PhotoAttemptRecord).order_by(PhotoAttemptRecord.number)
                )
            ).all()
            assert [item.outcome for item in attempts] == ["interrupted", "ready"]
            assert attempts[0].id != attempts[1].id
    finally:
        storage.release.set()
        if not task.done():
            task.cancel()
        await processor.close()


async def test_finalization_uses_fresh_database_time_not_prelock_timestamp(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    upload = await queued(identity_engine, owner, encoded())
    uow = SqlPhotoWorkerUnitOfWork(async_sessionmaker(identity_engine, expire_on_commit=False))
    async with uow.transaction() as transaction:
        at = await transaction.now()
        lease = await transaction.claim(at, at + timedelta(minutes=2))
    assert lease is not None
    async with async_sessionmaker(identity_engine).begin() as session:
        await session.execute(
            update(PhotoAttemptRecord)
            .where(PhotoAttemptRecord.id == lease.attempt_id)
            .values(lease_until=at + timedelta(microseconds=1))
        )
    async with uow.transaction() as transaction:
        assert (
            await transaction.complete(lease, PhotoImageInfo(1, 1, 1, bytes(range(32))), at)
            == PhotoProcessingStep.STALE
        )
    async with SqlMediaUnitOfWork(async_sessionmaker(identity_engine)).transaction() as transaction:
        assert await transaction.current_photo(owner.id) is None
        current = await transaction.upload(owner.id, upload.id)
        assert current is not None
        assert current.state == PhotoUploadState.PROCESSING


async def test_competing_workers_claim_a_queued_photo_once(identity_engine: AsyncEngine) -> None:
    owner = await actor(identity_engine)
    data = encoded()
    await queued(identity_engine, owner, data)
    storage = Storage(data)
    first, second = BoundedImageProcessor(), BoundedImageProcessor()
    try:
        outcomes = await asyncio.gather(
            worker(identity_engine, storage, first)(), worker(identity_engine, storage, second)()
        )
        assert set(outcomes) == {PhotoProcessingStep.READY, PhotoProcessingStep.IDLE}
    finally:
        await first.close()
        await second.close()
    async with async_sessionmaker(identity_engine)() as session:
        assert (
            await session.scalars(select(func.count()).select_from(PhotoAttemptRecord))
        ).one() == 1


async def test_busy_processor_does_not_claim_or_spend_attempt(identity_engine: AsyncEngine) -> None:
    owner = await actor(identity_engine)
    data = encoded()
    await queued(identity_engine, owner, data)
    processor = BoundedImageProcessor()
    await processor.close()
    assert await worker(identity_engine, Storage(data), processor)() == PhotoProcessingStep.BUSY
    async with async_sessionmaker(identity_engine)() as session:
        assert (
            await session.scalars(select(func.count()).select_from(PhotoAttemptRecord))
        ).one() == 0


@pytest.mark.parametrize("restriction", ["banned", "deleted", "revoked"])
async def test_ineligible_account_is_rejected_before_private_storage_read(
    identity_engine: AsyncEngine, restriction: str
) -> None:
    owner = await actor(identity_engine)
    data = encoded()
    upload = await queued(identity_engine, owner, data)
    async with async_sessionmaker(identity_engine).begin() as session:
        if restriction == "revoked":
            await session.execute(
                update(InstitutionalBindingRecord)
                .where(InstitutionalBindingRecord.account_id == owner.id)
                .values(revoked_at=func.clock_timestamp())
            )
        else:
            await session.execute(
                update(AccountRecord)
                .where(AccountRecord.id == owner.id)
                .values({restriction + "_at": func.clock_timestamp()})
            )
    storage = Storage(data)
    processor = BoundedImageProcessor()
    try:
        assert await worker(identity_engine, storage, processor)() == PhotoProcessingStep.REJECTED
    finally:
        await processor.close()
    assert not storage.started.is_set()
    async with SqlMediaUnitOfWork(async_sessionmaker(identity_engine)).transaction() as transaction:
        current = await transaction.upload(owner.id, upload.id)
        assert current is not None
        assert current.failure == PhotoFailure.ACCOUNT_UNAVAILABLE


async def test_expired_queued_upload_is_closed_without_storage_io(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    data = encoded()
    upload = await queued(identity_engine, owner, data)
    async with async_sessionmaker(identity_engine).begin() as session:
        await session.execute(
            update(PhotoUploadRecord).values(
                created_at=func.clock_timestamp() - timedelta(hours=2),
                upload_expires_at=func.clock_timestamp() - timedelta(minutes=90),
                processing_expires_at=func.clock_timestamp() - timedelta(hours=1),
            )
        )
    storage = Storage(data)
    processor = BoundedImageProcessor()
    try:
        assert await worker(identity_engine, storage, processor)() == PhotoProcessingStep.IDLE
    finally:
        await processor.close()
    assert not storage.started.is_set()
    async with SqlMediaUnitOfWork(async_sessionmaker(identity_engine)).transaction() as transaction:
        current = await transaction.upload(owner.id, upload.id)
        assert current is not None
        assert current.state == PhotoUploadState.EXPIRED


async def test_repeated_worker_crashes_do_not_create_unbounded_attempts(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    upload = await queued(identity_engine, owner, encoded())
    uow = SqlPhotoWorkerUnitOfWork(async_sessionmaker(identity_engine, expire_on_commit=False))
    for number in range(1, MAX_PHOTO_ATTEMPTS + 1):
        async with uow.transaction() as transaction:
            at = await transaction.now()
            lease = await transaction.claim(at, at + timedelta(minutes=2))
        assert lease is not None
        assert lease.attempts == number
        async with async_sessionmaker(identity_engine).begin() as session:
            await session.execute(
                update(PhotoAttemptRecord)
                .where(PhotoAttemptRecord.id == lease.attempt_id)
                .values(
                    started_at=func.clock_timestamp() - timedelta(minutes=2),
                    lease_until=func.clock_timestamp() - timedelta(minutes=1),
                )
            )
    async with uow.transaction() as transaction:
        at = await transaction.now()
        assert await transaction.claim(at, at + timedelta(minutes=2)) is None
    async with SqlMediaUnitOfWork(async_sessionmaker(identity_engine)).transaction() as transaction:
        current = await transaction.upload(owner.id, upload.id)
        assert current is not None
        assert current.failure == PhotoFailure.PROCESSING_UNAVAILABLE
    async with async_sessionmaker(identity_engine)() as session:
        assert (
            await session.scalars(select(func.count()).select_from(PhotoAttemptRecord))
        ).one() == MAX_PHOTO_ATTEMPTS


async def test_concurrent_photo_publications_compare_expected_version_under_account_lock(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    data = encoded()
    first = await queued(identity_engine, owner, data)
    second = await queued(identity_engine, owner, data)
    storage = Storage(data)
    left, right = BoundedImageProcessor(), BoundedImageProcessor()
    try:
        results = await asyncio.gather(
            worker(identity_engine, storage, left)(), worker(identity_engine, storage, right)()
        )
        assert set(results) == {PhotoProcessingStep.READY, PhotoProcessingStep.REJECTED}
    finally:
        await left.close()
        await right.close()
    async with SqlMediaUnitOfWork(async_sessionmaker(identity_engine)).transaction() as transaction:
        current = await transaction.current_photo(owner.id)
        assert current is not None
        assert current.version == 1
        assert current.upload_id in {first.id, second.id}
