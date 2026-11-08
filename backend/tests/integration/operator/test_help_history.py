"""Retained raw help snapshots under the real account audit and existing schema."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.help_history import ReadOperatorHelpHistory
from studymate.domain.catalogue import subject_key
from studymate.domain.operator.audit import OperatorAudit
from studymate.domain.operator.help_history import OPERATOR_HELP_HISTORY_PAGE_SIZE
from studymate.domain.study_context import HelpSubject, HelpSubjects
from studymate.infrastructure.operator.help_history_cursors import (
    FernetOperatorHelpHistoryCursorCodec,
)
from studymate.infrastructure.operator.help_history_transactions import (
    SqlOperatorHelpHistoryTransaction,
    SqlOperatorHelpHistoryUnitOfWork,
)
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.persistence.catalogue_models import SubjectRecord
from studymate.infrastructure.persistence.help_models import HelpRevisionRecord, HelpSelectionRecord
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from tests.integration.catalogue_fixture import subject
from tests.integration.operator.test_reads import operator
from tests.integration.requests.fixture import HASHER
from tests.integration.student_actor import Actor, actor
from tests.integration.test_help_subjects import command, services

pytestmark = pytest.mark.integration
CODEC = FernetOperatorHelpHistoryCursorCodec.from_key(b"h" * 32)
RAW_LABEL = "  Original saved help label  "
RAW_NOTE = " Private retained topic "
RAW_KEY = " Legacy MATCH ß unchanged "
CLEAR_VERSION = 2


@dataclass(frozen=True, slots=True)
class History:
    owner: Actor
    target: Actor
    subject_id: UUID
    second_subject_id: UUID
    uow: SqlOperatorHelpHistoryUnitOfWork

    def read(self) -> ReadOperatorHelpHistory:
        return ReadOperatorHelpHistory(self.uow, HASHER, CODEC)


async def prepared(engine: AsyncEngine) -> History:
    target = await actor(engine)
    first = await subject(engine, name="First synthetic help subject")
    second = await subject(engine, name="Second synthetic help subject")
    writer, _ = services(engine)
    await writer(
        command(
            target,
            HelpSubjects((HelpSubject(first.id, "Private original topic"), HelpSubject(second.id))),
        )
    )
    await writer(command(target, version=1))
    await writer(
        command(
            target,
            HelpSubjects((HelpSubject(first.id, "Later private topic"),)),
            version=CLEAR_VERSION,
        )
    )
    owner = await operator(engine)
    unit = SqlOperatorHelpHistoryUnitOfWork(
        async_sessionmaker(engine, expire_on_commit=False), record_operator_audit
    )
    return History(owner, target, first.id, second.id, unit)


async def test_exact_help_snapshots_survive_catalogue_change_target_lifecycle_and_clock_regression(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    renamed = "Current renamed archived catalogue subject"
    async with api.uow.sessions.begin() as session:
        await session.execute(
            update(HelpSelectionRecord)
            .where(
                HelpSelectionRecord.account_id == api.target.id,
                HelpSelectionRecord.version == 1,
                HelpSelectionRecord.subject_id == api.subject_id,
            )
            .values(subject_label=RAW_LABEL, topic_note=RAW_NOTE, topic_match_key=RAW_KEY)
        )
        await session.execute(
            update(HelpRevisionRecord)
            .where(HelpRevisionRecord.account_id == api.target.id, HelpRevisionRecord.version == 1)
            .values(saved_at=func.clock_timestamp() + timedelta(days=1))
        )
        await session.execute(
            update(SubjectRecord)
            .where(SubjectRecord.id == api.subject_id)
            .values(
                name=renamed,
                normalized_name=subject_key(renamed),
                archived_at=func.clock_timestamp(),
            )
        )
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == api.target.id)
            .values(banned_at=func.clock_timestamp(), deleted_at=func.clock_timestamp())
        )
    page = await api.read()(api.owner.credential, api.target.id)
    assert page is not None
    assert tuple(row.version for row in page.revisions) == (3, 2, 1)
    assert page.revisions[1].selections == ()
    raw = page.revisions[-1].selections[0]
    assert raw.subject_id == api.subject_id
    assert raw.subject_label == RAW_LABEL
    assert raw.topic_note == RAW_NOTE
    assert raw.topic_match_key == RAW_KEY
    assert page.revisions[-1].saved_at > page.revisions[0].saved_at
    assert page.revisions[0].selections[0].subject_label == "First synthetic help subject"
    async with api.uow.sessions() as session:
        audit = (await session.scalars(select(OperatorAuditRecord))).one()
        event = (
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        ).one()
        assert audit.action == "read_account"
        assert audit.requested_id == api.target.id
        assert audit.result_ids == [api.target.id]
        assert event.operator_action == "read_account"
        assert event.operator_audit_id == audit.id


async def test_existing_account_empty_history_saved_clear_and_missing_are_distinct(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    empty = await actor(identity_engine)
    clear = await actor(identity_engine)
    writer, _ = services(identity_engine)
    saved = await writer(command(clear))
    assert saved.revision.subjects.values == ()
    zero = await api.read()(api.owner.credential, empty.id)
    assert zero is not None
    assert zero.revisions == ()
    assert zero.anchor_version == 0
    cleared = await api.read()(api.owner.credential, clear.id)
    assert cleared is not None
    assert len(cleared.revisions) == 1
    assert cleared.revisions[0].selections == ()
    assert cleared.anchor_version == saved.revision.version
    missing = uuid4()
    assert await api.read()(api.owner.credential, missing) is None
    async with api.uow.sessions() as session:
        rows = tuple(await session.scalars(select(OperatorAuditRecord)))
        actual = next(row for row in rows if row.requested_id == empty.id)
        retained_clear = next(row for row in rows if row.requested_id == clear.id)
        absent = next(row for row in rows if row.requested_id == missing)
        assert actual.result_ids == [empty.id]
        assert retained_clear.result_ids == [clear.id]
        assert actual.outcome == retained_clear.outcome == "read"
        assert absent.outcome == "not_found"
        assert absent.result_ids == []


async def test_help_version_anchor_uses_all_rows_and_bulk_selection_slot_order_not_pointer(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    upper = OPERATOR_HELP_HISTORY_PAGE_SIZE + 2
    async with api.uow.sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        for version in range(4, upper + 1):
            session.add(HelpRevisionRecord(account_id=api.target.id, version=version, saved_at=now))
        await session.flush()
        session.add_all(
            (
                HelpSelectionRecord(
                    account_id=api.target.id,
                    version=upper,
                    slot=4,
                    subject_id=api.subject_id,
                    subject_label=RAW_LABEL,
                    topic_note=RAW_NOTE,
                    topic_match_key=RAW_KEY,
                ),
                HelpSelectionRecord(
                    account_id=api.target.id,
                    version=upper,
                    slot=1,
                    subject_id=api.second_subject_id,
                    subject_label="Second raw retained label",
                    topic_note=None,
                    topic_match_key=None,
                ),
            )
        )
    first = await api.read()(api.owner.credential, api.target.id)
    assert first is not None
    assert len(first.revisions) == OPERATOR_HELP_HISTORY_PAGE_SIZE
    assert first.anchor_version == upper
    assert tuple(value.slot for value in first.revisions[0].selections) == (1, 4)
    assert first.revisions[0].selections[-1].topic_match_key == RAW_KEY
    assert first.next_cursor is not None
    async with api.uow.sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        session.add(HelpRevisionRecord(account_id=api.target.id, version=upper + 1, saved_at=now))
    second = await api.read()(api.owner.credential, api.target.id, first.next_cursor)
    assert second is not None
    assert tuple(row.version for row in second.revisions) == (2, 1)
    assert second.revisions[0].selections == ()
    assert second.next_cursor is None
    refreshed = await api.read()(api.owner.credential, api.target.id)
    assert refreshed is not None
    assert refreshed.anchor_version == upper + 1
    assert refreshed.revisions[0].selections == ()


async def test_current_explicit_operator_required_before_any_help_history_sql(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    async with api.uow.sessions() as session:
        with pytest.raises(RuntimeError, match="operator"):
            await SqlOperatorHelpHistoryTransaction(
                session, record_operator_audit
            ).help_history_head(api.target.id)
    with pytest.raises(OperatorAccessDeniedError):
        await api.read()(api.target.credential, api.target.id)
    revoked = await operator(identity_engine, active=False)
    with pytest.raises(OperatorAccessDeniedError):
        await api.read()(revoked.credential, api.target.id)
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))


@pytest.mark.parametrize("cancel", [False, True])
async def test_help_history_canonical_error_or_cancel_rolls_back_and_releases_transaction(
    identity_engine: AsyncEngine,
    cancel: bool,
) -> None:
    api = await prepared(identity_engine)

    async def failing(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        if cancel:
            raise asyncio.CancelledError
        raise RuntimeError("Synthetic help history canonical failure")

    unit = SqlOperatorHelpHistoryUnitOfWork(api.uow.sessions, failing)
    with pytest.raises(asyncio.CancelledError if cancel else RuntimeError):
        await ReadOperatorHelpHistory(unit, HASHER, CODEC)(api.owner.credential, api.target.id)
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
        assert not tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        )
    assert await api.read()(api.owner.credential, api.target.id) is not None


async def test_actual_db_session_expiry_after_help_history_canonical_audit_returns_no_data(
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

    unit = SqlOperatorHelpHistoryUnitOfWork(api.uow.sessions, expired)
    with pytest.raises(UnauthenticatedError):
        await ReadOperatorHelpHistory(unit, HASHER, CODEC)(api.owner.credential, api.target.id)
    assert entered
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))


async def test_hidden_help_history_uses_privileged_role_not_current_contact_disclosure(
    identity_engine: AsyncEngine,
) -> None:
    from tests.integration.profile_lifecycle_fixture import (
        activated,
    )
    from tests.integration.profile_lifecycle_fixture import (
        command as hide_command,
    )
    from tests.integration.profile_lifecycle_fixture import (
        services as visibility_services,
    )

    target = await activated(identity_engine)
    writer, reader = services(identity_engine)
    current = await reader(target.credential)
    known = await subject(identity_engine)
    await writer(
        command(
            target,
            HelpSubjects((HelpSubject(known.id, "Private hidden note"),)),
            version=current.revision.version if current is not None else 0,
        )
    )
    visibility, _ = visibility_services(identity_engine)
    await visibility(hide_command(target))
    owner = await operator(identity_engine)
    unit = SqlOperatorHelpHistoryUnitOfWork(
        async_sessionmaker(identity_engine, expire_on_commit=False), record_operator_audit
    )
    page = await ReadOperatorHelpHistory(unit, HASHER, CODEC)(owner.credential, target.id)
    assert page is not None
    assert page.revisions[0].selections[0].topic_note == "Private hidden note"
