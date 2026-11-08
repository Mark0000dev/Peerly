"""Prepared only during hold; execute in uniquely migrated schemas after END."""

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.profile_history import ReadOperatorProfileHistory
from studymate.domain.operator.audit import OperatorAudit
from studymate.domain.operator.profile_history import OPERATOR_PROFILE_HISTORY_PAGE_SIZE
from studymate.domain.profiles import LanguageCode
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.operator.profile_history_cursors import (
    FernetOperatorProfileHistoryCursorCodec,
)
from studymate.infrastructure.operator.profile_history_transactions import (
    SqlOperatorProfileHistoryTransaction,
    SqlOperatorProfileHistoryUnitOfWork,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from studymate.infrastructure.persistence.profile_models import (
    ProfileLanguageRecord,
    ProfileRevisionRecord,
)
from tests.integration.operator.test_reads import operator
from tests.integration.requests.fixture import HASHER
from tests.integration.student_actor import Actor, actor
from tests.integration.test_profiles import command, services

pytestmark = pytest.mark.integration
CODEC = FernetOperatorProfileHistoryCursorCodec.from_key(b"h" * 32)
RAW_NAME = "  Retained Name  "
RAW_ABOUT = " Original private\n retained about  "


@dataclass(frozen=True, slots=True)
class History:
    owner: Actor
    target: Actor
    uow: SqlOperatorProfileHistoryUnitOfWork

    def read(self) -> ReadOperatorProfileHistory:
        return ReadOperatorProfileHistory(self.uow, HASHER, CODEC)


async def prepared(engine: AsyncEngine) -> History:
    target = await actor(engine)
    writer, _ = services(engine)
    for version, languages in enumerate((("ms", "en"), ("en",), ()), start=0):
        intent = command(target, version=version)
        await writer(
            replace(
                intent,
                basics=replace(
                    intent.basics, languages=tuple(LanguageCode(code) for code in languages)
                ),
            )
        )
    owner = await operator(engine)
    unit = SqlOperatorProfileHistoryUnitOfWork(
        async_sessionmaker(engine, expire_on_commit=False), record_operator_audit
    )
    return History(owner, target, unit)


async def test_banned_deleted_target_history_keeps_exact_fields_and_languages(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    async with api.uow.sessions.begin() as session:
        await session.execute(
            update(ProfileRevisionRecord)
            .where(
                ProfileRevisionRecord.account_id == api.target.id,
                ProfileRevisionRecord.version == 1,
            )
            .values(
                display_name=RAW_NAME,
                about=RAW_ABOUT,
                saved_at=func.clock_timestamp() + timedelta(days=1),
            )
        )
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == api.target.id)
            .values(banned_at=func.clock_timestamp(), deleted_at=func.clock_timestamp())
        )
    result = await api.read()(api.owner.credential, api.target.id)
    assert result is not None
    assert tuple(row.version for row in result.revisions) == (3, 2, 1)
    assert tuple(row.languages for row in result.revisions) == ((), ("en",), ("ms", "en"))
    assert result.revisions[-1].display_name == RAW_NAME
    assert result.revisions[-1].about == RAW_ABOUT
    assert result.revisions[-1].saved_at > result.revisions[0].saved_at
    async with api.uow.sessions() as session:
        inspection = (await session.scalars(select(OperatorAuditRecord))).one()
        event = (
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        ).one()
        assert inspection.action == "read_account"
        assert inspection.resource_kind == "account"
        assert inspection.requested_id == api.target.id
        assert inspection.result_ids == [api.target.id]
        assert event.operator_action == "read_account"
        assert event.operator_audit_id == inspection.id


async def test_actual_account_exists_empty_history_and_missing_account_have_distinct_audits(
    identity_engine: AsyncEngine,
) -> None:
    owner = await operator(identity_engine)
    target = await actor(identity_engine)
    unit = SqlOperatorProfileHistoryUnitOfWork(
        async_sessionmaker(identity_engine, expire_on_commit=False), record_operator_audit
    )
    reader = ReadOperatorProfileHistory(unit, HASHER, CODEC)
    page = await reader(owner.credential, target.id)
    assert page is not None
    assert page.revisions == ()
    assert page.anchor_version == 0
    missing = uuid4()
    assert await reader(owner.credential, missing) is None
    async with unit.sessions() as session:
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
        actual = next(row for row in audits if row.requested_id == target.id)
        absent = next(row for row in audits if row.requested_id == missing)
        assert actual.outcome == "read"
        assert actual.result_ids == [target.id]
        assert absent.outcome == "not_found"
        assert absent.result_ids == []


async def test_version_anchor_uses_all_retained_rows_and_bulk_languages(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    upper = OPERATOR_PROFILE_HISTORY_PAGE_SIZE + 2
    async with api.uow.sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        for version in range(4, upper + 1):
            session.add(
                ProfileRevisionRecord(
                    account_id=api.target.id,
                    version=version,
                    display_name=f"Retained {version}",
                    about=RAW_ABOUT,
                    programme=None,
                    year_label=None,
                    task="find_help",
                    saved_at=now,
                )
            )
        await session.flush()
        session.add_all(
            (
                ProfileLanguageRecord(account_id=api.target.id, version=upper, slot=4, code="en"),
                ProfileLanguageRecord(account_id=api.target.id, version=upper, slot=1, code="ms"),
            )
        )
    first = await api.read()(api.owner.credential, api.target.id)
    assert first is not None
    assert len(first.revisions) == OPERATOR_PROFILE_HISTORY_PAGE_SIZE
    assert first.anchor_version == upper
    assert first.revisions[0].languages == ("ms", "en")
    assert first.next_cursor is not None
    async with api.uow.sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        session.add(
            ProfileRevisionRecord(
                account_id=api.target.id,
                version=upper + 1,
                display_name="Later retained revision",
                about=None,
                programme=None,
                year_label=None,
                task="offer_help",
                saved_at=now,
            )
        )
    second = await api.read()(api.owner.credential, api.target.id, first.next_cursor)
    assert second is not None
    assert tuple(row.version for row in second.revisions) == (2, 1)
    assert second.next_cursor is None
    assert second.anchor_version == upper
    refresh = await api.read()(api.owner.credential, api.target.id)
    assert refresh is not None
    assert refresh.anchor_version == upper + 1
    assert refresh.revisions[0].task.value == "offer_help"


async def test_profile_history_direct_adapter_and_usecase_require_current_db_role(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    async with api.uow.sessions() as session:
        with pytest.raises(RuntimeError, match="operator"):
            await SqlOperatorProfileHistoryTransaction(
                session, record_operator_audit
            ).profile_history_head(api.target.id)
    with pytest.raises(OperatorAccessDeniedError):
        await api.read()(api.target.credential, api.target.id)
    revoked = await operator(identity_engine, active=False)
    with pytest.raises(OperatorAccessDeniedError):
        await api.read()(revoked.credential, api.target.id)
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))


@pytest.mark.parametrize("cancel", [False, True])
async def test_canonical_failure_or_cancellation_rolls_back_entire_history_inspection(
    identity_engine: AsyncEngine,
    cancel: bool,
) -> None:
    api = await prepared(identity_engine)

    async def fail(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        if cancel:
            raise asyncio.CancelledError
        raise RuntimeError("Synthetic history canonical failure")

    unit = SqlOperatorProfileHistoryUnitOfWork(api.uow.sessions, fail)
    with pytest.raises(asyncio.CancelledError if cancel else RuntimeError):
        await ReadOperatorProfileHistory(unit, HASHER, CODEC)(api.owner.credential, api.target.id)
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
        assert not tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        )
    assert await api.read()(api.owner.credential, api.target.id) is not None


async def test_actual_session_expiry_after_canonical_history_audit_returns_no_content(
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
        await session.execute(select(func.pg_sleep(1.1)))

    unit = SqlOperatorProfileHistoryUnitOfWork(api.uow.sessions, expire)
    with pytest.raises(UnauthenticatedError):
        await ReadOperatorProfileHistory(unit, HASHER, CODEC)(api.owner.credential, api.target.id)
    assert entered
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
        assert not tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        )


async def test_actual_hidden_profile_history_remains_readable_without_public_disclosure_grant(
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
    owner = await operator(identity_engine)
    visibility, _ = visibility_services(identity_engine)
    await visibility(hide_command(target))
    unit = SqlOperatorProfileHistoryUnitOfWork(
        async_sessionmaker(identity_engine, expire_on_commit=False), record_operator_audit
    )
    page = await ReadOperatorProfileHistory(unit, HASHER, CODEC)(owner.credential, target.id)
    assert page is not None
    assert page.revisions
    assert all(row.account_id == target.id for row in page.revisions)
    assert page.revisions[0].display_name is not None
    async with unit.sessions() as session:
        inspection = (await session.scalars(select(OperatorAuditRecord))).one()
        assert inspection.requested_id == target.id
        assert inspection.result_ids == [target.id]
