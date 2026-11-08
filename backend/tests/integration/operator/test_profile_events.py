"""Real canonical helpers and owned revision FKs projected through audited timeline reads."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.operator.timeline import ReadOperatorEvent, SearchOperatorEvents
from studymate.application.operator.timeline_ports import OperatorEventFilters
from studymate.application.ports.http_tracing import HttpExecution
from studymate.domain.media import PhotoRevision
from studymate.domain.operator.audit import OperatorAudit
from studymate.domain.operator.timeline import (
    OperatorEventFacts,
    OperatorEventKind,
    OperatorSourceKind,
)
from studymate.domain.profiles import DisplayName, OnboardingTask, ProfileBasics, ProfileRevision
from studymate.domain.study_context import HelpRevision, HelpSubjects
from studymate.infrastructure.observability.tracing import OtelHttpTracing
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.operator.timeline_cursors import FernetOperatorEventCursorCodec
from studymate.infrastructure.operator.timeline_transactions import SqlOperatorTimelineUnitOfWork
from studymate.infrastructure.persistence.help_models import HelpRevisionRecord
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.media_models import (
    PhotoRevisionRecord,
    PhotoUploadRevisionRecord,
)
from studymate.infrastructure.persistence.media_origin_models import MediaOriginRecord
from studymate.infrastructure.persistence.photo_attempt_models import PhotoAttemptRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import (
    record_help_saved,
    record_operator_audit,
    record_photo_published,
    record_profile_saved,
)
from studymate.infrastructure.persistence.profile_models import ProfileRevisionRecord
from tests.integration.operator.test_photo_uploads import DIGEST, seed_upload
from tests.integration.operator.test_reads import operator
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration
CODEC = FernetOperatorEventCursorCodec.from_key(b"t" * 32)
PRIVATE_ABOUT = "Private saved profile body must not enter the canonical timeline"
KINDS = (
    OperatorEventKind.PROFILE_SAVED,
    OperatorEventKind.HELP_SAVED,
    OperatorEventKind.PHOTO_PUBLISHED,
)
SOURCE_VERSION = 7


@dataclass(frozen=True, slots=True)
class Sources:
    profile: ProfileRevision
    help: HelpRevision
    photo: PhotoRevision


async def sources(session: AsyncSession, owner: UUID) -> Sources:
    at = await session.scalar(select(func.clock_timestamp()))
    assert isinstance(at, datetime)
    session.add(
        ProfileRevisionRecord(
            account_id=owner,
            version=SOURCE_VERSION,
            display_name="Synthetic retained name",
            about=PRIVATE_ABOUT,
            programme=None,
            year_label=None,
            task="find_help",
            saved_at=at,
        )
    )
    session.add(HelpRevisionRecord(account_id=owner, version=SOURCE_VERSION, saved_at=at))
    upload_id = await seed_upload(session, owner, at)
    attempt_id = uuid4()
    session.add(
        PhotoAttemptRecord(
            id=attempt_id,
            upload_id=upload_id,
            number=1,
            started_at=at,
            lease_until=at + timedelta(minutes=1),
            finished_at=at,
            next_attempt_at=None,
            outcome="ready",
            failure=None,
            display_width=32,
            display_height=24,
            display_size=42,
            display_digest=DIGEST,
        )
    )
    await session.flush()
    session.add(
        PhotoUploadRevisionRecord(
            upload_id=upload_id,
            account_id=owner,
            version=2,
            state="ready",
            updated_at=at,
            attempt_id=attempt_id,
            failure=None,
        )
    )
    await session.flush()
    session.add(
        PhotoRevisionRecord(
            account_id=owner,
            version=SOURCE_VERSION,
            upload_id=upload_id,
            upload_version=2,
            upload_state="ready",
            saved_at=at,
        )
    )
    await session.flush()
    return Sources(
        ProfileRevision(
            owner,
            SOURCE_VERSION,
            ProfileBasics(DisplayName("Synthetic retained name"), about=PRIVATE_ABOUT),
            OnboardingTask.FIND_HELP,
            at,
        ),
        HelpRevision(owner, SOURCE_VERSION, HelpSubjects(), at),
        PhotoRevision(owner, SOURCE_VERSION, upload_id, at),
    )


async def append_sources(session: AsyncSession, values: Sources) -> None:
    await record_profile_saved(session, values.profile)
    await record_help_saved(session, values.help)
    await record_photo_published(session, values.photo)


@pytest.mark.parametrize("retained_origin", [True, False])
async def test_exact_canonical_source_refs_original_origins_and_deleted_target_retention(
    identity_engine: AsyncEngine, retained_origin: bool
) -> None:
    target = await actor(identity_engine)
    viewer = await operator(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    request_id, action_id, queued_id = uuid4(), uuid4(), uuid4()
    tracing = OtelHttpTracing()
    async with sessions.begin() as session:
        values = await sources(session, target.id)
        if retained_origin:
            session.add(
                MediaOriginRecord(
                    upload_id=values.photo.upload_id,
                    phase="queued",
                    request_id=queued_id,
                    action_id=None,
                    trace_id=None,
                    span_id=None,
                    recorded_at=values.photo.saved_at,
                )
            )
            await session.flush()
        with tracing.start(HttpExecution(request_id, action_id, "POST", None)):
            await append_sources(session, values)
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == target.id)
            .values(banned_at=func.clock_timestamp(), deleted_at=func.clock_timestamp())
        )
    uow = SqlOperatorTimelineUnitOfWork(sessions, record_operator_audit)
    search = SearchOperatorEvents(uow, HASHER, FINGERPRINTER, CODEC)
    seen = []
    for kind, source_kind in zip(
        KINDS,
        (OperatorSourceKind.PROFILE, OperatorSourceKind.HELP, OperatorSourceKind.PHOTO),
        strict=True,
    ):
        page = await search(
            viewer.credential, OperatorEventFilters(subject_account_id=target.id, kind=kind)
        )
        assert len(page.events) == 1
        event = page.events[0]
        assert event.kind == kind
        assert event.facts == OperatorEventFacts()
        assert len(event.sources) == 1
        source = event.sources[0]
        assert source.kind == source_kind
        assert source.id == source.owner_id == target.id
        assert source.version == SOURCE_VERSION
        assert event.initiator_account_id is None
        actual = await ReadOperatorEvent(uow, HASHER)(viewer.credential, event.id)
        assert actual == event
        if kind == OperatorEventKind.PHOTO_PUBLISHED:
            assert event.origin.http_request_id == (queued_id if retained_origin else None)
            assert event.origin.action_id is None
        else:
            assert event.origin.http_request_id == request_id
            assert event.origin.action_id == action_id
        seen.append(event.id)
    assert PRIVATE_ABOUT not in repr(page)
    async with sessions() as session:
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
        assert len(audits) == len(KINDS) * 2
        assert all(row.result_ids[0] in seen for row in audits)
        canonical = tuple(
            await session.scalars(
                select(ProductEventRecord).where(
                    ProductEventRecord.kind.in_([kind.value for kind in KINDS])
                )
            )
        )
        assert len(canonical) == len(KINDS)
        assert all(
            row.schema_version == 1 and row.subject_id is None and row.onboarding_task is None
            for row in canonical
        )


async def test_canonical_and_source_rows_roll_back_together_before_operator_visibility(
    identity_engine: AsyncEngine,
) -> None:
    target = await actor(identity_engine)
    viewer = await operator(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)

    async def aborted_owner_transaction() -> None:
        async with sessions.begin() as session:
            values = await sources(session, target.id)
            await append_sources(session, values)
            raise RuntimeError("synthetic owner rollback")

    with pytest.raises(RuntimeError, match="synthetic owner rollback"):
        await aborted_owner_transaction()
    async with sessions() as session:
        assert not tuple(await session.scalars(select(ProfileRevisionRecord)))
        assert not tuple(await session.scalars(select(HelpRevisionRecord)))
        assert not tuple(await session.scalars(select(PhotoRevisionRecord)))
        assert not tuple(await session.scalars(select(ProductEventRecord)))
    search = SearchOperatorEvents(
        SqlOperatorTimelineUnitOfWork(sessions, record_operator_audit), HASHER, FINGERPRINTER, CODEC
    )
    page = await search(viewer.credential, OperatorEventFilters(subject_account_id=target.id))
    assert page.events == ()


@pytest.mark.parametrize("kind", KINDS)
async def test_operator_audit_failure_does_not_return_new_family_or_commit_inspection(
    identity_engine: AsyncEngine, kind: OperatorEventKind
) -> None:
    target = await actor(identity_engine)
    viewer = await operator(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        values = await sources(session, target.id)
        await append_sources(session, values)

    async def fail(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        raise RuntimeError("synthetic canonical audit failure")

    search = SearchOperatorEvents(
        SqlOperatorTimelineUnitOfWork(sessions, fail), HASHER, FINGERPRINTER, CODEC
    )
    with pytest.raises(RuntimeError, match="synthetic canonical audit failure"):
        await search(
            viewer.credential, OperatorEventFilters(subject_account_id=target.id, kind=kind)
        )
    async with sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
        assert await session.scalar(select(func.count()).select_from(ProductEventRecord)) == len(
            KINDS
        )
