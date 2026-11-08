"""Canonical profile-media binary reads against actual head43 and synthetic retained objects."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import AsyncAdaptedQueuePool

from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.media.storage import (
    MediaObjectMissingError,
    MediaStorageUnavailableError,
)
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.media_read import ReadOperatorProfileMedia
from studymate.application.operator.timeline import ReadOperatorAudit
from studymate.domain.media import MediaObjectRef
from studymate.domain.operator.audit import OperatorAudit
from studymate.domain.operator.profile_media import (
    OperatorProfileMediaKind,
    OperatorProfileMediaRequest,
)
from studymate.infrastructure.operator.media_transactions import (
    SqlOperatorProfileMediaTransaction,
    SqlOperatorProfileMediaUnitOfWork,
)
from studymate.infrastructure.operator.models import (
    OperatorAccessRecord,
    OperatorAccessRevisionRecord,
    OperatorAuditRecord,
)
from studymate.infrastructure.operator.timeline_transactions import SqlOperatorTimelineUnitOfWork
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord
from studymate.infrastructure.persistence.photo_attempt_models import PhotoAttemptRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from studymate.presentation.operator.timeline_models import audit_response
from tests.integration.operator.test_photo_uploads import seed_upload
from tests.integration.operator.test_reads import operator
from tests.integration.profile_lifecycle_fixture import activated
from tests.integration.profile_lifecycle_fixture import command as hidden_command
from tests.integration.profile_lifecycle_fixture import services as visibility_services
from tests.integration.requests.fixture import HASHER
from tests.integration.student_actor import Actor, actor

pytestmark = pytest.mark.integration
PRIVATE_BINARY = b"synthetic-private-retained-profile-object"


@dataclass(slots=True)
class RetainedReader:
    engine: AsyncEngine
    objects: dict[MediaObjectRef, bytes] = field(default_factory=dict, repr=False)
    references: list[MediaObjectRef] = field(default_factory=list)
    callback: Callable[[], Awaitable[None]] | None = None
    unavailable: bool = False
    stopped: bool = False

    async def read(self, reference: MediaObjectRef) -> bytes:
        pool = self.engine.pool
        assert isinstance(pool, AsyncAdaptedQueuePool)
        assert pool.checkedout() == 0
        self.references.append(reference)
        try:
            if self.callback is not None:
                await self.callback()
            if self.unavailable:
                raise MediaStorageUnavailableError
            if reference not in self.objects:
                raise MediaObjectMissingError
            return self.objects[reference]
        finally:
            self.stopped = True


@dataclass(frozen=True, slots=True)
class Media:
    owner: Actor
    target: Actor
    request: OperatorProfileMediaRequest
    uow: SqlOperatorProfileMediaUnitOfWork
    reader: RetainedReader

    def read(self) -> ReadOperatorProfileMedia:
        return ReadOperatorProfileMedia(self.uow, HASHER, self.reader)


async def prepared(engine: AsyncEngine, *, target: Actor | None = None) -> Media:
    target = target if target is not None else await actor(engine)
    viewer = await operator(engine)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        upload_id = await seed_upload(session, target.id, now, state="rejected")
        attempt_id = uuid4()
        session.add(
            PhotoAttemptRecord(
                id=attempt_id,
                upload_id=upload_id,
                number=1,
                started_at=now,
                lease_until=now + timedelta(minutes=1),
                finished_at=now,
                next_attempt_at=None,
                outcome="stale",
                failure=None,
                display_width=None,
                display_height=None,
                display_size=None,
                display_digest=None,
            )
        )
    request = OperatorProfileMediaRequest(
        target.id, upload_id, attempt_id, OperatorProfileMediaKind.ORIGINAL
    )
    reader = RetainedReader(
        engine,
        {
            replace(request, kind=kind).reference: PRIVATE_BINARY
            for kind in OperatorProfileMediaKind
        },
    )
    return Media(
        viewer,
        target,
        request,
        SqlOperatorProfileMediaUnitOfWork(sessions, record_operator_audit),
        reader,
    )


async def media_audits(api: Media) -> tuple[OperatorAuditRecord, ...]:
    async with api.uow.sessions() as session:
        return tuple(
            await session.scalars(
                select(OperatorAuditRecord).where(OperatorAuditRecord.action == "read_media")
            )
        )


@pytest.mark.parametrize("kind", list(OperatorProfileMediaKind))
async def test_actual_failed_stale_retained_objects_unverified_operator_deleted_target_and_audit(
    kind: OperatorProfileMediaKind, identity_engine: AsyncEngine
) -> None:
    api = await prepared(identity_engine)
    async with api.uow.sessions.begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == api.target.id)
            .values(banned_at=func.clock_timestamp(), deleted_at=func.clock_timestamp())
        )
    request = replace(api.request, kind=kind)
    result = await api.read()(api.owner.credential, request)
    assert result is not None
    assert result.data == PRIVATE_BINARY
    rows = await media_audits(api)
    assert len(rows) == 1
    audit = rows[0]
    assert audit.resource_kind == "profile_media"
    assert audit.result_ids == [request.upload_id]
    assert audit.requested_media_owner_id == api.target.id
    assert audit.requested_media_attempt_id == request.attempt_id
    assert audit.requested_media_kind == kind.value
    assert audit.actual_source_upload_id == request.upload_id
    async with api.uow.sessions() as session:
        event = (
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.operator_audit_id == audit.id)
            )
        ).one()
        assert event.operator_action == "read_media"
    detail = await ReadOperatorAudit(
        SqlOperatorTimelineUnitOfWork(api.uow.sessions, record_operator_audit), HASHER
    )(api.owner.credential, audit.id)
    assert detail is not None
    dto = audit_response(detail)
    assert dto.requested_media_kind == kind
    assert dto.requested_media_owner_id == api.target.id
    assert dto.actual_source_upload_id == request.upload_id
    assert "sha256" not in dto.model_dump_json()
    assert PRIVATE_BINARY.decode() not in dto.model_dump_json()


async def test_actual_hidden_target_does_not_remove_retained_operator_access(
    identity_engine: AsyncEngine,
) -> None:
    target = await activated(identity_engine)
    visibility, _ = visibility_services(identity_engine)
    await visibility(hidden_command(target))
    api = await prepared(identity_engine, target=target)
    result = await api.read()(api.owner.credential, api.request)
    assert result is not None
    assert result.data == PRIVATE_BINARY


@pytest.mark.parametrize("missing", ["owner", "upload", "attempt", "blob"])
async def test_unknown_or_foreign_source_and_missing_blob_are_truthfully_audited(
    missing: str, identity_engine: AsyncEngine
) -> None:
    api = await prepared(identity_engine)
    request = api.request
    if missing == "owner":
        request = replace(request, account_id=uuid4())
    elif missing == "upload":
        request = replace(request, upload_id=uuid4())
    elif missing == "attempt":
        request = replace(request, attempt_id=uuid4())
    else:
        api.reader.objects.clear()
    assert await api.read()(api.owner.credential, request) is None
    rows = await media_audits(api)
    assert len(rows) == 1
    assert rows[0].outcome == "not_found"
    assert rows[0].result_ids == []
    assert rows[0].requested_id == request.upload_id
    assert rows[0].requested_media_owner_id == request.account_id
    assert rows[0].actual_source_upload_id == (request.upload_id if missing == "blob" else None)
    assert bool(api.reader.references) == (missing == "blob")


async def test_owner_and_attempt_relation_cannot_be_substituted(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    other = await prepared(identity_engine)
    request = replace(api.request, attempt_id=other.request.attempt_id)
    assert await api.read()(api.owner.credential, request) is None
    assert not api.reader.references
    assert (await media_audits(api))[0].actual_source_upload_id is None


@pytest.mark.parametrize(
    "change", ["revoked", "regranted", "banned", "deleted", "session_revoked", "session_expired"]
)
async def test_final_authority_rechecks_after_storage_and_grant_write_is_unblocked(
    change: str, identity_engine: AsyncEngine
) -> None:
    api = await prepared(identity_engine)

    async def changed() -> None:
        async with api.uow.sessions.begin() as session:
            await session.execute(
                select(AccountRecord.id).where(AccountRecord.id == api.owner.id).with_for_update()
            )
            await session.execute(
                select(SessionRecord.id)
                .where(SessionRecord.account_id == api.owner.id)
                .with_for_update()
            )
            now = await session.scalar(select(func.clock_timestamp()))
            assert isinstance(now, datetime)
            if change in ("revoked", "regranted"):
                root = await session.scalar(
                    select(OperatorAccessRecord)
                    .where(OperatorAccessRecord.account_id == api.owner.id)
                    .with_for_update()
                )
                assert root is not None
                root.current_version = 2
                session.add(
                    OperatorAccessRevisionRecord(
                        account_id=api.owner.id,
                        version=2,
                        active=change == "regranted",
                        changed_at=now,
                    )
                )
            elif change == "banned":
                await session.execute(
                    update(AccountRecord)
                    .where(AccountRecord.id == api.owner.id)
                    .values(banned_at=now)
                )
            elif change == "deleted":
                await session.execute(
                    update(AccountRecord)
                    .where(AccountRecord.id == api.owner.id)
                    .values(deleted_at=now)
                )
            elif change == "session_revoked":
                await session.execute(
                    update(SessionRecord)
                    .where(SessionRecord.account_id == api.owner.id)
                    .values(revoked_at=now)
                )
            else:
                await session.execute(
                    update(SessionRecord)
                    .where(SessionRecord.account_id == api.owner.id)
                    .values(expires_at=now)
                )

    api.reader.callback = changed
    error = (
        OperatorAccessDeniedError
        if change in ("revoked", "regranted", "banned")
        else UnauthenticatedError
    )
    with pytest.raises(error):
        await api.read()(api.owner.credential, api.request)
    assert api.reader.stopped
    assert not await media_audits(api)


async def test_single_connection_pool_can_execute_core_sql_during_object_io(
    identity_engine: AsyncEngine,
) -> None:
    async with identity_engine.connect() as connection:
        schema = await connection.scalar(select(func.current_schema()))
        assert isinstance(schema, str)
    bounded = create_async_engine(
        identity_engine.url,
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.25,
        connect_args={"server_settings": {"search_path": schema}},
    )
    try:
        api = await prepared(bounded)
        completed = False

        async def core_query() -> None:
            nonlocal completed
            async with api.uow.sessions() as session:
                assert (
                    await session.scalar(
                        select(AccountRecord.id).where(AccountRecord.id == api.target.id)
                    )
                    == api.target.id
                )
            completed = True

        api.reader.callback = core_query
        result = await api.read()(api.owner.credential, api.request)
        assert result is not None
        assert completed
    finally:
        await bounded.dispose()


async def test_source_absence_after_io_does_not_use_stale_permission(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)

    async def missing() -> None:
        # Isolated synthetic corruption probe only; production never purges retained sources.
        async with api.uow.sessions.begin() as session:
            await session.execute(
                delete(PhotoAttemptRecord).where(PhotoAttemptRecord.id == api.request.attempt_id)
            )

    api.reader.callback = missing
    assert await api.read()(api.owner.credential, api.request) is None
    row = (await media_audits(api))[0]
    assert row.outcome == "not_found"
    assert row.actual_source_upload_id is None


async def test_actual_canonical_audit_failure_rolls_back_and_never_returns_data(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)

    async def failed(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        raise StorageUnavailableError

    uow = replace(api.uow, recorder=failed)
    with pytest.raises(StorageUnavailableError):
        await ReadOperatorProfileMedia(uow, HASHER, api.reader)(api.owner.credential, api.request)
    assert not await media_audits(api)
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(ProductEventRecord)))


async def test_session_expiry_after_final_audit_crosses_real_database_clock(
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

    async def expired(session: AsyncSession, audit: OperatorAudit) -> None:
        nonlocal entered
        await record_operator_audit(session, audit)
        entered = True
        await session.execute(select(func.pg_sleep(1.1)))

    uow = replace(api.uow, recorder=expired)
    with pytest.raises(UnauthenticatedError):
        await ReadOperatorProfileMedia(uow, HASHER, api.reader)(api.owner.credential, api.request)
    assert entered
    assert not await media_audits(api)
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(ProductEventRecord)))


@pytest.mark.parametrize("phase", ["storage", "audit"])
async def test_cancellation_drains_storage_or_rolls_back_audit_and_releases_pool(
    phase: str, identity_engine: AsyncEngine
) -> None:
    api = await prepared(identity_engine)
    entered = asyncio.Event()
    pause = asyncio.Event()

    async def blocked() -> None:
        entered.set()
        await pause.wait()

    async def paused(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        entered.set()
        await pause.wait()

    if phase == "storage":
        api.reader.callback = blocked
    uow = replace(api.uow, recorder=paused) if phase == "audit" else api.uow
    task = asyncio.create_task(
        ReadOperatorProfileMedia(uow, HASHER, api.reader)(api.owner.credential, api.request)
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
    assert api.reader.stopped
    assert not await media_audits(api)
    api.reader.callback = None
    retry = await asyncio.wait_for(api.read()(api.owner.credential, api.request), timeout=5)
    assert retry is not None


async def test_media_sql_without_checked_operator_is_not_a_grant(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    async with api.uow.sessions() as session:
        with pytest.raises(RuntimeError, match="operator"):
            await SqlOperatorProfileMediaTransaction(
                session, record_operator_audit
            ).profile_media_source(api.request)


@pytest.mark.parametrize(
    "fault",
    [
        "owner",
        "attempt",
        "requested",
        "old_action",
        "missing_source",
        "missing_owner",
        "transport",
        "empty_results",
    ],
)
async def test_real_database_media_audit_shape_and_owned_source_constraints(
    fault: str, identity_engine: AsyncEngine
) -> None:
    api = await prepared(identity_engine)

    async def invalid() -> None:
        async with api.uow.sessions.begin() as session:
            now = await session.scalar(select(func.clock_timestamp()))
            assert isinstance(now, datetime)
            row = OperatorAuditRecord(
                id=uuid4(),
                operator_id=api.owner.id,
                operator_access_version=1,
                operator_access_active=True,
                action="read_media",
                resource_kind="profile_media",
                requested_id=api.request.upload_id,
                result_ids=[api.request.upload_id],
                outcome="read",
                query_fingerprint=None,
                occurred_at=now,
                requested_media_owner_id=api.target.id,
                requested_media_attempt_id=api.request.attempt_id,
                requested_media_kind="original",
                actual_source_upload_id=api.request.upload_id,
            )
            if fault == "owner":
                row.requested_media_owner_id = uuid4()
            elif fault == "attempt":
                row.requested_media_attempt_id = uuid4()
            elif fault == "requested":
                row.requested_id = uuid4()
                row.result_ids = [row.requested_id]
            elif fault == "old_action":
                row.action = "read_account"
                row.resource_kind = "account"
            elif fault == "missing_source":
                row.actual_source_upload_id = None
            elif fault == "missing_owner":
                row.requested_media_owner_id = None
            elif fault == "transport":
                row.requested_media_kind = "upload"
            else:
                row.result_ids = []
            session.add(row)
            await session.flush()

    with pytest.raises(IntegrityError):
        await invalid()
    assert not await media_audits(api)


async def test_deferred_commit_failure_after_canonical_audit_never_returns_bytes(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    staged = False

    async def invalid_commit(session: AsyncSession, audit: OperatorAudit) -> None:
        nonlocal staged
        await record_operator_audit(session, audit)
        # Isolated fault injection: this real FK is DEFERRABLE INITIALLY DEFERRED.
        # The successful flush/audit must not release bytes before commit fails.
        await session.execute(
            update(OperatorAccessRecord)
            .where(OperatorAccessRecord.account_id == api.owner.id)
            .values(current_version=2)
        )
        await session.flush()
        staged = True

    failing = replace(api.uow, recorder=invalid_commit)
    with pytest.raises(IntegrityError, match="fk_operator_access_current_revision"):
        await ReadOperatorProfileMedia(failing, HASHER, api.reader)(
            api.owner.credential, api.request
        )
    assert staged
    assert not await media_audits(api)
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(ProductEventRecord)))
        assert (
            await session.scalar(
                select(OperatorAccessRecord.current_version).where(
                    OperatorAccessRecord.account_id == api.owner.id
                )
            )
            == 1
        )
    retry = await api.read()(api.owner.credential, api.request)
    assert retry is not None
    assert len(await media_audits(api)) == 1
