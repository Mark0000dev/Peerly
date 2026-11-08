import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.media.cleanup import CleanupMediaTransport, TransportCleanupStep
from studymate.application.media.uploads import PhotoUploadCommand, UploadAction
from studymate.domain.media import MediaObjectKind
from studymate.infrastructure.media.images import BoundedImageProcessor
from studymate.infrastructure.persistence.media_models import (
    PhotoUploadRecord,
    PhotoUploadRevisionRecord,
)
from studymate.infrastructure.persistence.transport_cleanup import SqlTransportCleanupUnitOfWork
from studymate.infrastructure.persistence.transport_cleanup_models import TransportCleanupRecord
from tests.image_fixture import encoded
from tests.integration.media_fixture import Storage, command, queued, services, worker
from tests.integration.migrations import migrate
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration


def cleaner(engine: AsyncEngine, storage: Storage) -> CleanupMediaTransport:
    return CleanupMediaTransport(
        SqlTransportCleanupUnitOfWork(async_sessionmaker(engine, expire_on_commit=False)), storage
    )


async def age_transport(engine: AsyncEngine) -> None:
    now = datetime.now(UTC)
    async with async_sessionmaker(engine).begin() as session:
        await session.execute(
            update(PhotoUploadRecord).values(
                created_at=now - timedelta(minutes=20),
                upload_expires_at=now - timedelta(minutes=5),
                processing_expires_at=now + timedelta(minutes=40),
            )
        )
        await session.execute(
            update(TransportCleanupRecord).values(next_attempt_at=now - timedelta(minutes=5))
        )


async def test_cleanup_waits_for_signed_access_expiry_and_pending_processing(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    storage = Storage(encoded())
    upload = await queued(identity_engine, owner, storage.data)
    cleanup = cleaner(identity_engine, storage)
    assert await cleanup() == TransportCleanupStep.IDLE
    await age_transport(identity_engine)
    assert await cleanup() == TransportCleanupStep.IDLE
    assert not storage.removed
    _, change, _ = services(identity_engine)
    await change(
        PhotoUploadCommand(
            owner.credential, upload.id, UploadAction.CANCEL, IntentKey(str(uuid4()))
        )
    )
    assert await cleanup() == TransportCleanupStep.CLEANED
    assert [ref.kind for ref in storage.removed] == [MediaObjectKind.UPLOAD]


async def test_cleanup_never_deletes_retained_original_display_or_current_photo(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    storage = Storage(encoded())
    upload = await queued(identity_engine, owner, storage.data)
    processor = BoundedImageProcessor()
    try:
        await worker(identity_engine, storage, processor)()
    finally:
        await processor.close()
    retained = storage.retained.copy()
    await age_transport(identity_engine)
    cleanup = cleaner(identity_engine, storage)
    assert await cleanup() == TransportCleanupStep.CLEANED
    assert await cleanup() == TransportCleanupStep.IDLE
    assert storage.retained == retained
    assert len(storage.removed) == 1
    assert storage.removed[0].upload_id == upload.id
    assert storage.removed[0].kind == MediaObjectKind.UPLOAD
    async with async_sessionmaker(identity_engine)() as session:
        record = await session.get(TransportCleanupRecord, upload.id)
        assert record is not None
        assert record.cleaned_at is not None
        assert record.generation is None
        assert record.lease_until is None


async def test_cleanup_storage_outage_persists_backoff_then_recovers(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    start, _, _ = services(identity_engine)
    upload = await start(command(owner))
    await age_transport(identity_engine)
    storage = Storage(b"", unavailable=True)
    cleanup = cleaner(identity_engine, storage)
    assert await cleanup() == TransportCleanupStep.RETRY
    assert await cleanup() == TransportCleanupStep.IDLE
    async with async_sessionmaker(identity_engine).begin() as session:
        record = await session.get(TransportCleanupRecord, upload.id)
        assert record is not None
        assert record.attempts == 1
        assert record.cleaned_at is None
        record.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    storage.unavailable = False
    assert await cleanup() == TransportCleanupStep.CLEANED


async def test_cleanup_reclaim_generation_fences_old_acknowledgement(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    start, _, _ = services(identity_engine)
    upload = await start(command(owner))
    await age_transport(identity_engine)
    uow = SqlTransportCleanupUnitOfWork(async_sessionmaker(identity_engine, expire_on_commit=False))
    async with uow.transaction() as transaction:
        at = await transaction.now()
        first = await transaction.claim(at, at + timedelta(minutes=1))
    assert first is not None
    async with async_sessionmaker(identity_engine).begin() as session:
        await session.execute(
            update(TransportCleanupRecord)
            .where(TransportCleanupRecord.upload_id == upload.id)
            .values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
        )
    async with uow.transaction() as transaction:
        at = await transaction.now()
        second = await transaction.claim(at, at + timedelta(minutes=1))
    assert second is not None
    assert second.generation != first.generation
    async with uow.transaction() as transaction:
        assert not await transaction.finish(first, await transaction.now(), None)
        assert await transaction.finish(second, await transaction.now(), None)
    async with uow.transaction() as transaction:
        assert not await transaction.finish(second, await transaction.now(), None)


async def test_competing_cleanup_workers_claim_once(identity_engine: AsyncEngine) -> None:
    owner = await actor(identity_engine)
    start, _, _ = services(identity_engine)
    await start(command(owner))
    await age_transport(identity_engine)
    storage = Storage(b"")
    outcomes = await asyncio.gather(
        cleaner(identity_engine, storage)(), cleaner(identity_engine, storage)()
    )
    assert set(outcomes) == {TransportCleanupStep.CLEANED, TransportCleanupStep.IDLE}
    assert len(storage.removed) == 1


async def test_cleanup_revision_backfills_existing_intents_without_altering_source(
    engine: AsyncEngine,
) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(migrate, "0011_photo_attempts")
    owner = await actor(engine)
    now, upload_id = datetime.now(UTC), uuid4()
    async with async_sessionmaker(engine).begin() as session:
        session.add(
            PhotoUploadRecord(
                id=upload_id,
                account_id=owner.id,
                current_version=1,
                expected_photo_version=0,
                source_size=10,
                source_digest=bytes(range(32)),
                content_type="image/png",
                created_at=now,
                upload_expires_at=now + timedelta(minutes=15),
                processing_expires_at=now + timedelta(hours=1),
            )
        )
        await session.flush()
        session.add(
            PhotoUploadRevisionRecord(
                upload_id=upload_id,
                version=1,
                account_id=owner.id,
                state="uploading",
                updated_at=now,
            )
        )
    async with engine.begin() as connection:
        await connection.run_sync(migrate, "head")
    async with async_sessionmaker(engine)() as session:
        backfilled = (await session.scalars(select(TransportCleanupRecord))).one()
        assert backfilled.upload_id == upload_id
        assert backfilled.attempts == 0
        assert backfilled.next_attempt_at == now + timedelta(minutes=15)
        source = await session.get(PhotoUploadRecord, upload_id)
        assert source is not None
        assert source.source_digest == bytes(range(32))
