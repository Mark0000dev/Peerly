"""Actual migrated profile-media tables, without a storage client or binary access grant."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.cursors import InvalidOperatorCursorError
from studymate.application.operator.photo_ports import OperatorPhotoFilters
from studymate.application.operator.photo_uploads import (
    ReadOperatorPhotoHistory,
    ReadOperatorPhotoUploads,
)
from studymate.domain.media import PhotoUploadState
from studymate.domain.operator.audit import OperatorAudit
from studymate.domain.operator.photo_uploads import OPERATOR_PHOTO_PAGE_SIZE
from studymate.infrastructure.media.images import BoundedImageProcessor
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.operator.photo_cursors import FernetOperatorPhotoCursorCodec
from studymate.infrastructure.operator.photo_transactions import (
    SqlOperatorPhotoTransaction,
    SqlOperatorPhotoUnitOfWork,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord
from studymate.infrastructure.persistence.media_models import (
    PhotoRevisionRecord,
    PhotoUploadRecord,
    PhotoUploadRevisionRecord,
)
from studymate.infrastructure.persistence.media_origin_models import MediaOriginRecord
from studymate.infrastructure.persistence.photo_attempt_models import PhotoAttemptRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from tests.image_fixture import encoded
from tests.integration.media_fixture import Storage, command, queued, services, worker
from tests.integration.operator.test_reads import operator
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.student_actor import Actor, actor

pytestmark = pytest.mark.integration
CODEC = FernetOperatorPhotoCursorCodec.from_key(b"p" * 32)
DIGEST = bytes(range(32))
LAST_ATTEMPT = 3
LATEST_PUBLICATION = 3


@dataclass(frozen=True, slots=True)
class Photos:
    owner: Actor
    target: Actor
    upload_id: UUID
    uow: SqlOperatorPhotoUnitOfWork

    def roots(self) -> ReadOperatorPhotoUploads:
        return ReadOperatorPhotoUploads(self.uow, HASHER, FINGERPRINTER, CODEC)

    def history(self) -> ReadOperatorPhotoHistory:
        return ReadOperatorPhotoHistory(self.uow, HASHER, CODEC)


async def prepared(engine: AsyncEngine) -> Photos:
    target = await actor(engine)
    start, _, _ = services(engine)
    upload = await start(command(target))
    owner = await operator(engine)
    return Photos(
        owner,
        target,
        upload.id,
        SqlOperatorPhotoUnitOfWork(
            async_sessionmaker(engine, expire_on_commit=False), record_operator_audit
        ),
    )


async def seed_upload(
    session: AsyncSession, owner: UUID, at: datetime, *, state: str = "uploading"
) -> UUID:
    upload_id = uuid4()
    session.add(
        PhotoUploadRecord(
            id=upload_id,
            account_id=owner,
            current_version=1,
            expected_photo_version=0,
            source_size=10,
            source_digest=DIGEST,
            content_type="image/png",
            created_at=at,
            upload_expires_at=at + timedelta(minutes=5),
            processing_expires_at=at + timedelta(hours=1),
        )
    )
    await session.flush()
    session.add(
        PhotoUploadRevisionRecord(
            upload_id=upload_id,
            account_id=owner,
            version=1,
            state=state,
            updated_at=at,
            attempt_id=None,
            failure="invalid_image" if state == "rejected" else None,
        )
    )
    await session.flush()
    return upload_id


async def test_all_raw_history_not_current_pointer_and_deleted_account_retention(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    async with api.uow.sessions.begin() as session:
        source = await session.get(PhotoUploadRecord, api.upload_id)
        assert source is not None
        for version in range(2, OPERATOR_PHOTO_PAGE_SIZE + 3):
            session.add(
                PhotoUploadRevisionRecord(
                    upload_id=source.id,
                    account_id=api.target.id,
                    version=version,
                    state="cancelled",
                    updated_at=source.created_at - timedelta(minutes=version),
                    attempt_id=None,
                    failure=None,
                )
            )
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == api.target.id)
            .values(banned_at=func.clock_timestamp(), deleted_at=func.clock_timestamp())
        )
    page = await api.history()(api.owner.credential, api.target.id, api.upload_id)
    assert page is not None
    assert page.next_cursor is not None
    assert page.anchor_version == OPERATOR_PHOTO_PAGE_SIZE + 2
    assert page.upload.current_version == 1
    assert page.revisions[0].updated_at < page.revisions[-1].updated_at
    assert page.upload.source_sha256 == DIGEST
    assert repr(DIGEST) not in repr(page)
    second = await api.history()(
        api.owner.credential, api.target.id, api.upload_id, page.next_cursor
    )
    assert second is not None
    assert second.next_cursor is None
    assert tuple(row.version for row in second.revisions) == (2, 1)
    assert second.attempts_current == ()
    assert second.origins == ()
    assert second.latest_published_photo_ref is None
    async with api.uow.sessions() as session:
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
        assert all(
            row.requested_id == api.target.id and row.result_ids == [api.target.id]
            for row in audits
        )
        assert len(audits) == len((page, second))
        assert await session.scalar(
            select(func.count())
            .select_from(ProductEventRecord)
            .where(ProductEventRecord.kind == "operator.inspected")
        ) == len(audits)


async def test_root_keyset_filters_stored_state_all_unpublished_and_metadata_anchor(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    async with api.uow.sessions.begin() as session:
        at = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(at, datetime)
        for index in range(OPERATOR_PHOTO_PAGE_SIZE + 2):
            await seed_upload(
                session,
                api.target.id,
                at + timedelta(minutes=index),
                state="rejected" if index % 2 else "cancelled",
            )
    page = await api.roots()(api.owner.credential, api.target.id, OperatorPhotoFilters())
    assert page is not None
    assert page.next_cursor is not None
    assert len(page.uploads) == OPERATOR_PHOTO_PAGE_SIZE
    assert page.anchor_created_at is not None
    assert page.anchor_created_at > page.observed_at
    async with api.uow.sessions.begin() as session:
        newer = await seed_upload(
            session, api.target.id, page.anchor_created_at + timedelta(days=1)
        )
    second = await api.roots()(
        api.owner.credential, api.target.id, OperatorPhotoFilters(), page.next_cursor
    )
    assert second is not None
    assert second.next_cursor is None
    assert newer not in {row.id for row in second.uploads}
    assert api.upload_id in {row.id for row in second.uploads}
    filters = OperatorPhotoFilters(
        PhotoUploadState.REJECTED, created_from=at, created_before=at + timedelta(minutes=3)
    )
    failed = await api.roots()(api.owner.credential, api.target.id, filters)
    assert failed is not None
    assert len(failed.uploads) == 1
    assert failed.uploads[0].current_revision.failure is not None
    with pytest.raises(InvalidOperatorCursorError):
        await api.roots()(api.owner.credential, api.target.id, filters, page.next_cursor)


async def test_bounded_attempts_actual_origins_and_only_latest_publication(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    async with api.uow.sessions.begin() as session:
        source = await session.get(PhotoUploadRecord, api.upload_id)
        assert source is not None
        at = source.created_at
        ids = tuple(uuid4() for _ in range(3))
        for number, attempt_id in enumerate(ids, 1):
            session.add(
                PhotoAttemptRecord(
                    id=attempt_id,
                    upload_id=source.id,
                    number=number,
                    started_at=at,
                    lease_until=at + timedelta(minutes=1),
                    finished_at=at,
                    next_attempt_at=at + timedelta(seconds=1) if number == 1 else None,
                    outcome="retry"
                    if number == 1
                    else "ready"
                    if number == LAST_ATTEMPT
                    else "interrupted",
                    failure="storage_unavailable" if number == 1 else None,
                    display_width=32 if number == LAST_ATTEMPT else None,
                    display_height=24 if number == LAST_ATTEMPT else None,
                    display_size=42 if number == LAST_ATTEMPT else None,
                    display_digest=DIGEST if number == LAST_ATTEMPT else None,
                )
            )
        await session.flush()
        session.add(
            PhotoUploadRevisionRecord(
                upload_id=source.id,
                account_id=api.target.id,
                version=2,
                state="processing",
                updated_at=at,
                attempt_id=ids[0],
                failure=None,
            )
        )
        session.add(
            PhotoUploadRevisionRecord(
                upload_id=source.id,
                account_id=api.target.id,
                version=3,
                state="ready",
                updated_at=at,
                attempt_id=ids[-1],
                failure=None,
            )
        )
        await session.flush()
        for version in range(1, 4):
            session.add(
                PhotoRevisionRecord(
                    account_id=api.target.id,
                    version=version,
                    upload_id=source.id,
                    upload_version=3,
                    upload_state="ready",
                    saved_at=at,
                )
            )
        for phase in ("created", "queued"):
            session.add(
                MediaOriginRecord(
                    upload_id=source.id,
                    phase=phase,
                    request_id=uuid4(),
                    action_id=None,
                    trace_id=None,
                    span_id=None,
                    recorded_at=at,
                )
            )
    detail = await api.history()(api.owner.credential, api.target.id, api.upload_id)
    assert detail is not None
    assert tuple(row.number for row in detail.attempts_current) == (1, 2, 3)
    assert detail.revisions[1].attempt_id == detail.attempts_current[0].id
    assert detail.attempts_current[0].outcome.value == "retry"
    assert detail.attempts_current[-1].display_sha256 == DIGEST
    assert {row.phase.value for row in detail.origins} == {"created", "queued"}
    assert detail.latest_published_photo_ref is not None
    assert detail.latest_published_photo_ref.photo_version == LATEST_PUBLICATION
    async with api.uow.sessions.begin() as session:
        await session.execute(
            update(PhotoAttemptRecord)
            .where(PhotoAttemptRecord.id == ids[0])
            .values(outcome="interrupted", next_attempt_at=None)
        )
    changed = await api.history()(api.owner.credential, api.target.id, api.upload_id)
    assert changed is not None
    assert changed.revisions == detail.revisions
    assert changed.attempts_current[0].outcome.value == "interrupted"


async def test_actual_photo_worker_metadata_not_object_availability_claim(
    identity_engine: AsyncEngine,
) -> None:
    target = await actor(identity_engine)
    data = encoded()
    source = await queued(identity_engine, target, data)
    storage = Storage(data)
    processor = BoundedImageProcessor()
    try:
        result = await worker(identity_engine, storage, processor)()
    finally:
        await processor.close()
    assert result is not None
    owner = await operator(identity_engine)
    uow = SqlOperatorPhotoUnitOfWork(
        async_sessionmaker(identity_engine, expire_on_commit=False), record_operator_audit
    )
    storage.retained.clear()
    page = await ReadOperatorPhotoHistory(uow, HASHER, CODEC)(
        owner.credential, target.id, source.id
    )
    assert page is not None
    assert page.upload.current_revision.state == PhotoUploadState.READY
    assert page.latest_published_photo_ref is not None
    assert page.attempts_current[0].display_width is not None
    assert page.attempts_current[0].display_sha256 is not None
    assert not storage.accesses


async def test_missing_account_empty_and_foreign_upload_audits_actual_parent(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    empty = await actor(identity_engine)
    assert await api.history()(api.owner.credential, empty.id, api.upload_id) is None
    child = await api.history()(api.owner.credential, api.target.id, uuid4())
    assert child is None
    missing = uuid4()
    assert await api.roots()(api.owner.credential, missing, OperatorPhotoFilters()) is None
    listing = await api.roots()(api.owner.credential, empty.id, OperatorPhotoFilters())
    assert listing is not None
    assert listing.uploads == ()
    async with api.uow.sessions() as session:
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
        unknown = next(row for row in audits if row.requested_id == missing)
        assert unknown.outcome == "not_found"
        assert unknown.result_ids == []
        assert all(
            row.outcome == "read" and row.result_ids == [row.requested_id]
            for row in audits
            if row.requested_id != missing
        )


async def test_audit_failure_rolls_back_audit_and_canonical_before_return(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)

    async def fail(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        raise RuntimeError("synthetic post-canonical failure")

    failed = SqlOperatorPhotoUnitOfWork(api.uow.sessions, fail)
    with pytest.raises(RuntimeError, match="synthetic post-canonical"):
        await ReadOperatorPhotoHistory(failed, HASHER, CODEC)(
            api.owner.credential, api.target.id, api.upload_id
        )
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
        assert not tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        )


@pytest.mark.parametrize("denial", ["role", "expired"])
async def test_no_implicit_role_or_expired_session_read(
    identity_engine: AsyncEngine, denial: str
) -> None:
    api = await prepared(identity_engine)
    viewer = api.target if denial == "role" else api.owner
    if denial == "expired":
        async with api.uow.sessions.begin() as session:
            await session.execute(
                update(SessionRecord)
                .where(SessionRecord.account_id == viewer.id)
                .values(expires_at=func.clock_timestamp())
            )
    error = OperatorAccessDeniedError if denial == "role" else UnauthenticatedError
    with pytest.raises(error):
        await api.history()(viewer.credential, api.target.id, api.upload_id)
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))


async def test_sql_requires_actual_checked_operator_access(identity_engine: AsyncEngine) -> None:
    async with async_sessionmaker(identity_engine)() as session:
        transaction = SqlOperatorPhotoTransaction(session, record_operator_audit)
        with pytest.raises(RuntimeError):
            await transaction.photo_account(uuid4())


async def test_final_auth_after_actual_canonical_write_rolls_everything_back(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    async with api.uow.sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        await session.execute(
            update(SessionRecord)
            .where(SessionRecord.account_id == api.owner.id)
            .values(expires_at=now + timedelta(seconds=1))
        )
    entered = False

    async def expire(session: AsyncSession, audit: OperatorAudit) -> None:
        nonlocal entered
        await record_operator_audit(session, audit)
        entered = True
        # Cross the real captured DB-clock session deadline, not an ORM snapshot mutation.
        await session.execute(select(func.pg_sleep(1.1)))

    failed = SqlOperatorPhotoUnitOfWork(api.uow.sessions, expire)
    with pytest.raises(UnauthenticatedError):
        await ReadOperatorPhotoHistory(failed, HASHER, CODEC)(
            api.owner.credential, api.target.id, api.upload_id
        )
    assert entered
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
        assert not tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        )


async def test_cancel_after_actual_canonical_write_rolls_back_and_releases_locks(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    entered = asyncio.Event()
    pause = asyncio.Event()

    async def paused(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        entered.set()
        await pause.wait()

    uow = SqlOperatorPhotoUnitOfWork(api.uow.sessions, paused)
    task = asyncio.create_task(
        ReadOperatorPhotoHistory(uow, HASHER, CODEC)(
            api.owner.credential, api.target.id, api.upload_id
        )
    )
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        if not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
        assert not tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        )
    retry = await asyncio.wait_for(
        api.history()(api.owner.credential, api.target.id, api.upload_id), timeout=5
    )
    assert retry is not None


async def test_passed_upload_deadlines_do_not_rewrite_recorded_state(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    async with api.uow.sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        old = await seed_upload(session, api.target.id, now - timedelta(days=1))
    page = await api.roots()(
        api.owner.credential, api.target.id, OperatorPhotoFilters(PhotoUploadState.UPLOADING)
    )
    assert page is not None
    stored = next(row for row in page.uploads if row.id == old)
    assert stored.processing_expires_at < page.observed_at
    assert stored.current_revision.state == PhotoUploadState.UPLOADING
    async with api.uow.sessions() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(PhotoUploadRevisionRecord)
                .where(PhotoUploadRevisionRecord.upload_id == old)
            )
            == 1
        )
