"""PostgreSQL pagination/filter/history sources under real operator authority."""

from datetime import datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.errors import StorageUnavailableError
from studymate.application.idempotency import IntentKey
from studymate.application.support.operator import (
    ChangeOperatorSupportStatus,
    ChangeSupportStatusCommand,
)
from studymate.application.support.operator_inbox import (
    ReadOperatorSupportHistory,
    SearchOperatorSupportCases,
)
from studymate.application.support.operator_inbox_ports import OperatorSupportFilters
from studymate.domain.operator.audit import OperatorAudit
from studymate.domain.support.cases import SupportStatus, SupportTopic
from studymate.domain.support.operator_inbox import OPERATOR_SUPPORT_PAGE_SIZE
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import (
    record_operator_audit,
    record_support_event,
)
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from studymate.infrastructure.support.models import (
    SupportCaseRecord,
    SupportProofRecord,
    SupportRevisionRecord,
)
from studymate.infrastructure.support.operator import SqlOperatorSupportUnitOfWork
from studymate.infrastructure.support.operator_inbox_cursors import (
    FernetOperatorSupportInboxCursorCodec,
)
from studymate.infrastructure.support.operator_inbox_transactions import (
    SqlOperatorSupportInboxUnitOfWork,
)
from tests.integration.operator.test_reads import operator
from tests.integration.student_actor import Actor, actor

pytestmark = pytest.mark.integration
CODEC = FernetOperatorSupportInboxCursorCodec.from_key(b"k" * 32)
HASHER = Sha256SessionHasher()
FINGERPRINTER = HmacIntentFingerprinter(b"h" * 32)
HISTORY_ANCHOR = OPERATOR_SUPPORT_PAGE_SIZE + 2


async def seed_sources(engine: AsyncEngine, owner: Actor) -> Actor:
    retained = await actor(engine, verified=False)
    async with async_sessionmaker(engine).begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == retained.id)
            .values(deleted_at=now, banned_at=now)
        )
        # Historical business fixtures only; schema always comes from real head migrations.
        for index in range(OPERATOR_SUPPORT_PAGE_SIZE + 1):
            digest = (index + 1).to_bytes(32, "big")
            session.add(
                SupportProofRecord(
                    digest=digest,
                    source_digest=digest,
                    created_at=now,
                    expires_at=now + timedelta(days=7),
                )
            )
        await session.flush()
        for index in range(OPERATOR_SUPPORT_PAGE_SIZE + 1):
            session.add(
                SupportCaseRecord(
                    id=UUID(int=index + 1),
                    proof_digest=(index + 1).to_bytes(32, "big"),
                    actor_id=retained.id if index == 0 else None,
                    topic=SupportTopic.CANNOT_SIGN_IN.value,
                    reply_address="PRIVATE@example.test",
                    message="PRIVATE_SUPPORT_BODY",
                    details="PRIVATE_DETAILS",
                    received_at=now,
                )
            )
        await session.flush()
        for index in range(OPERATOR_SUPPORT_PAGE_SIZE + 1):
            session.add(
                SupportRevisionRecord(
                    case_id=UUID(int=index + 1), version=1, status="received", changed_at=now
                )
            )
        for version in range(2, HISTORY_ANCHOR + 1):
            session.add(
                SupportRevisionRecord(
                    case_id=UUID(int=1),
                    version=version,
                    status="resolved",
                    changed_at=now,
                    changed_by_id=owner.id,
                    operator_access_version=1,
                )
            )
    return retained


async def test_real_keyset_filters_current_status_retained_actor_and_immutable_history_anchor(
    identity_engine: AsyncEngine,
) -> None:
    owner = await operator(identity_engine)
    retained = await seed_sources(identity_engine, owner)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    uow = SqlOperatorSupportInboxUnitOfWork(sessions, record_operator_audit)
    search = SearchOperatorSupportCases(uow, HASHER, FINGERPRINTER, CODEC)
    first = await search(owner.credential, OperatorSupportFilters())
    assert len(first.cases) == OPERATOR_SUPPORT_PAGE_SIZE
    assert first.next_cursor is not None
    assert [row.receipt.case_id.int for row in first.cases] == list(
        range(OPERATOR_SUPPORT_PAGE_SIZE + 1, 1, -1)
    )
    second = await search(owner.credential, OperatorSupportFilters(), first.next_cursor)
    assert [row.receipt.case_id for row in second.cases] == [UUID(int=1)]
    assert second.next_cursor is None
    selected = await search(
        owner.credential,
        OperatorSupportFilters(
            actor_id=retained.id,
            status=SupportStatus.RESOLVED,
            topic=SupportTopic.CANNOT_SIGN_IN,
            anonymous=False,
        ),
    )
    assert selected.cases == second.cases
    assert not (
        await search(
            owner.credential,
            OperatorSupportFilters(received_before=first.cases[0].receipt.received_at),
        )
    ).cases
    assert (
        len((await search(owner.credential, OperatorSupportFilters(anonymous=True))).cases)
        == OPERATOR_SUPPORT_PAGE_SIZE
    )
    history = ReadOperatorSupportHistory(uow, HASHER, CODEC)
    original = await history(owner.credential, UUID(int=1))
    assert original is not None
    assert original.anchor_version == HISTORY_ANCHOR
    assert original.next_cursor is not None
    change = ChangeOperatorSupportStatus(
        SqlOperatorSupportUnitOfWork(sessions, record_support_event, record_operator_audit),
        HASHER,
        FINGERPRINTER,
    )
    changed = await change(
        ChangeSupportStatusCommand(
            owner.credential,
            UUID(int=1),
            SupportStatus.IN_REVIEW,
            HISTORY_ANCHOR,
            IntentKey("history_append_001"),
        )
    )
    assert changed is not None
    remainder = await history(owner.credential, UUID(int=1), original.next_cursor)
    assert remainder is not None
    assert remainder.anchor_version == HISTORY_ANCHOR
    assert [row.receipt.version for row in remainder.revisions] == [2, 1]
    assert remainder.revisions[-1].changed_by_id is None
    assert remainder.revisions[0].changed_by_id == owner.id
    refreshed = await history(owner.credential, UUID(int=1))
    assert refreshed is not None
    assert refreshed.anchor_version == changed.version
    assert not (
        await search(owner.credential, OperatorSupportFilters(status=SupportStatus.RESOLVED))
    ).cases


async def fail_canonical_audit(session: AsyncSession, audit: OperatorAudit) -> None:
    await record_operator_audit(session, audit)
    raise StorageUnavailableError


async def test_real_inbox_audit_and_canonical_failure_rolls_back_without_returning_sources(
    identity_engine: AsyncEngine,
) -> None:
    owner = await operator(identity_engine)
    await seed_sources(identity_engine, owner)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    uow = SqlOperatorSupportInboxUnitOfWork(sessions, fail_canonical_audit)
    with pytest.raises(StorageUnavailableError):
        await SearchOperatorSupportCases(uow, HASHER, FINGERPRINTER, CODEC)(
            owner.credential, OperatorSupportFilters()
        )
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(OperatorAuditRecord)) == 0
        assert await session.scalar(select(func.count()).select_from(ProductEventRecord)) == 0
