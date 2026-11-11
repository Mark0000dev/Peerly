import asyncio
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.accounts import ReadOperatorAccount, SearchOperatorAccounts
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.filters import OperatorAccountFilters, OperatorAccountLifecycle
from studymate.application.operator.messages import ReadOperatorConversationMessages
from studymate.domain.identity import StudentEmail
from studymate.domain.membership import GOOGLE_ISSUER
from studymate.domain.operator.audit import OPERATOR_ACCOUNT_PAGE_SIZE, OperatorAudit
from studymate.infrastructure.operator.cursors import FernetOperatorCursorCodec
from studymate.infrastructure.operator.models import (
    OperatorAccessRecord,
    OperatorAccessRevisionRecord,
    OperatorAuditRecord,
)
from studymate.infrastructure.operator.transactions import SqlOperatorUnitOfWork
from studymate.infrastructure.persistence.discovery_freshness_models import DiscoveryExposureRecord
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
    SessionRecord,
)
from studymate.infrastructure.persistence.message_read_models import ConversationReadPositionRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.onboarding_fixture import ready_setup
from tests.integration.student_actor import Actor, actor
from tests.integration.test_message_commands import chat

pytestmark = pytest.mark.integration
HASHER = Sha256SessionHasher()
CODEC = FernetOperatorCursorCodec.from_key(b"s" * 32)
MISSING_READS = 2
FINGERPRINT_BYTES = 32
INITIAL_GRANT = 1


async def operator(engine: AsyncEngine, *, active: bool = True) -> Actor:
    owner = await actor(engine, verified=False)
    async with async_sessionmaker(engine).begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        session.add(
            ExternalIdentityRecord(
                id=uuid4(),
                account_id=owner.id,
                issuer=GOOGLE_ISSUER,
                subject=f"synthetic-{owner.id}",
                created_at=now,
            )
        )
        await session.flush()
        session.add(OperatorAccessRecord(account_id=owner.id, current_version=1))
        await session.flush()
        session.add(
            OperatorAccessRevisionRecord(
                account_id=owner.id,
                version=1,
                active=active,
                changed_at=now,
            )
        )
    return owner


def uow(engine: AsyncEngine) -> SqlOperatorUnitOfWork:
    return SqlOperatorUnitOfWork(
        async_sessionmaker(engine, expire_on_commit=False), record_operator_audit
    )


async def test_explicit_unverified_operator_reads_deleted_target_with_atomic_audit(
    identity_engine: AsyncEngine,
) -> None:
    owner = await operator(identity_engine)
    target = await actor(identity_engine)
    async with async_sessionmaker(identity_engine).begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == target.id)
            .values(
                banned_at=func.clock_timestamp(),
                deleted_at=func.clock_timestamp(),
            )
        )
    detail = await ReadOperatorAccount(uow(identity_engine), HASHER)(owner.credential, target.id)
    assert detail is not None
    assert detail.account.account_id == target.id
    assert detail.account.deleted_at is not None
    assert detail.account.banned_at is not None
    async with async_sessionmaker(identity_engine)() as session:
        audit = (await session.scalars(select(OperatorAuditRecord))).one()
        event = (await session.scalars(select(ProductEventRecord))).one()
        assert audit.operator_id == owner.id
        assert audit.result_ids == [target.id]
        assert event.operator_audit_id == audit.id
        assert event.kind == "operator.inspected"
        assert not tuple(await session.scalars(select(DiscoveryExposureRecord)))


@pytest.mark.parametrize("denial", ["absent", "revoked", "banned", "deleted"])
async def test_no_implicit_role_or_lifecycle_bypass(
    identity_engine: AsyncEngine, denial: str
) -> None:
    owner = (
        await actor(identity_engine)
        if denial == "absent"
        else await operator(identity_engine, active=denial != "revoked")
    )
    if denial in {"banned", "deleted"}:
        async with async_sessionmaker(identity_engine).begin() as session:
            statement = update(AccountRecord).where(AccountRecord.id == owner.id)
            await session.execute(
                statement.values(
                    banned_at=func.clock_timestamp() if denial == "banned" else None,
                    deleted_at=func.clock_timestamp() if denial == "deleted" else None,
                )
            )
    error = UnauthenticatedError if denial == "deleted" else OperatorAccessDeniedError
    with pytest.raises(error):
        await ReadOperatorAccount(uow(identity_engine), HASHER)(owner.credential, uuid4())
    async with async_sessionmaker(identity_engine)() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
        assert not tuple(await session.scalars(select(ProductEventRecord)))


async def test_missing_resources_commit_not_found_before_controller404(
    identity_engine: AsyncEngine,
) -> None:
    owner = await operator(identity_engine)
    assert (
        await ReadOperatorAccount(uow(identity_engine), HASHER)(owner.credential, uuid4()) is None
    )
    assert (
        await ReadOperatorConversationMessages(uow(identity_engine), HASHER, CODEC)(
            owner.credential, uuid4()
        )
        is None
    )
    async with async_sessionmaker(identity_engine)() as session:
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
        assert len(audits) == MISSING_READS
        assert all(audit.outcome == "not_found" and not audit.result_ids for audit in audits)
        assert len(tuple(await session.scalars(select(ProductEventRecord)))) == MISSING_READS


async def test_canonical_failure_rolls_back_audit_and_does_not_return_data(
    identity_engine: AsyncEngine,
) -> None:
    owner = await operator(identity_engine)

    async def fail(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        raise RuntimeError("synthetic canonical failure")

    failing = SqlOperatorUnitOfWork(
        async_sessionmaker(identity_engine, expire_on_commit=False), fail
    )
    with pytest.raises(RuntimeError, match="synthetic canonical failure"):
        await ReadOperatorAccount(failing, HASHER)(owner.credential, owner.id)
    async with async_sessionmaker(identity_engine)() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
        assert not tuple(await session.scalars(select(ProductEventRecord)))


async def test_search_retains_only_hmac_and_actual_returned_ids(
    identity_engine: AsyncEngine,
) -> None:
    owner = await operator(identity_engine)
    target = await actor(identity_engine)
    search = SearchOperatorAccounts(
        uow(identity_engine), HASHER, HmacIntentFingerprinter(b"s" * 32), CODEC
    )
    page = await search(owner.credential, OperatorAccountFilters(account_id=target.id))
    assert [row.account_id for row in page.accounts] == [target.id]
    assert page.next_cursor is None
    async with async_sessionmaker(identity_engine)() as session:
        audit = (await session.scalars(select(OperatorAuditRecord))).one()
        assert audit.query_fingerprint is not None
        assert len(audit.query_fingerprint) == FINGERPRINT_BYTES
        assert audit.result_ids == [target.id]
        assert audit.requested_id is None


async def test_nonparticipant_inspection_keeps_full_text_without_read_ack_or_activity(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    sent = await owned.send()(owned.command())
    assert sent.message is not None
    owner = await operator(identity_engine)
    async with owned.api.sessions.begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == owned.sender.id)
            .values(
                banned_at=func.clock_timestamp(),
                deleted_at=func.clock_timestamp(),
            )
        )
    page = await ReadOperatorConversationMessages(uow(identity_engine), HASHER, CODEC)(
        owner.credential, owned.conversation_id
    )
    assert page is not None
    assert page.messages == (sent.message,)
    assert page.anchor_sequence == sent.message.sequence
    async with owned.api.sessions() as session:
        audit = (await session.scalars(select(OperatorAuditRecord))).one()
        assert audit.result_ids == [sent.message.id]
        assert audit.requested_id == owned.conversation_id
        assert not tuple(await session.scalars(select(ConversationReadPositionRecord)))
        assert await session.get(DiscoveryExposureRecord, owner.id) is None


async def test_account_keyset_excludes_new_insert_and_audits_only_returned_page(
    identity_engine: AsyncEngine,
) -> None:
    owner = await operator(identity_engine)
    async with async_sessionmaker(identity_engine).begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        ids = {uuid4() for _ in range(22)}
        session.add_all(AccountRecord(id=value, created_at=now) for value in ids)
    search = SearchOperatorAccounts(
        uow(identity_engine), HASHER, HmacIntentFingerprinter(b"s" * 32), CODEC
    )
    first = await search(owner.credential, OperatorAccountFilters())
    assert len(first.accounts) == OPERATOR_ACCOUNT_PAGE_SIZE
    assert first.next_cursor is not None
    inserted = await actor(identity_engine)
    second = await search(owner.credential, OperatorAccountFilters(), first.next_cursor)
    combined = [row.account_id for row in first.accounts + second.accounts]
    assert len(combined) == len(set(combined))
    assert set(combined) == ids | {owner.id}
    assert inserted.id not in combined
    assert second.next_cursor is None
    async with async_sessionmaker(identity_engine)() as session:
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
        assert {tuple(audit.result_ids) for audit in audits} == {
            tuple(row.account_id for row in page.accounts) for page in (first, second)
        }


async def test_session_expiry_after_audit_prevents_response_and_rolls_back(
    identity_engine: AsyncEngine,
) -> None:
    owner = await operator(identity_engine)

    async with async_sessionmaker(identity_engine).begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        await session.execute(
            update(SessionRecord)
            .where(SessionRecord.account_id == owner.id)
            .values(
                expires_at=now + timedelta(seconds=1),
            )
        )

    async def expire(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        # Actual database time passes the captured session deadline under its lock.
        await session.execute(select(func.pg_sleep(1.1)))

    failing = SqlOperatorUnitOfWork(
        async_sessionmaker(identity_engine, expire_on_commit=False), expire
    )
    with pytest.raises(UnauthenticatedError):
        await ReadOperatorAccount(failing, HASHER)(owner.credential, owner.id)
    async with async_sessionmaker(identity_engine)() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
        assert not tuple(await session.scalars(select(ProductEventRecord)))


@pytest.mark.parametrize(
    "kind", ["google", "email", "name", "hidden", "active", "banned", "deleted", "time"]
)
async def test_account_filters_use_stored_sources_not_student_disclosure(
    identity_engine: AsyncEngine,
    kind: str,
) -> None:
    owner = await operator(identity_engine)
    target = await actor(identity_engine)
    await ready_setup(identity_engine, target.credential)
    async with async_sessionmaker(identity_engine).begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        link_id = uuid4()
        session.add(
            ExternalIdentityRecord(
                id=link_id,
                account_id=target.id,
                issuer=GOOGLE_ISSUER,
                subject=f"synthetic-{target.id}",
                created_at=now,
            )
        )
        if kind in {"banned", "deleted"}:
            await session.execute(
                update(AccountRecord)
                .where(AccountRecord.id == target.id)
                .values(
                    banned_at=now if kind == "banned" else None,
                    deleted_at=now if kind == "deleted" else None,
                )
            )
    choices = {
        "google": OperatorAccountFilters(
            google_link_id=link_id, google_subject=f"synthetic-{target.id}"
        ),
        "email": OperatorAccountFilters(
            institutional_email=StudentEmail(f"synthetic-{target.id.hex}@mail.apu.edu.my")
        ),
        "name": OperatorAccountFilters(name="Synthetic student"),
        "hidden": OperatorAccountFilters(account_id=target.id, hidden=False),
        "active": OperatorAccountFilters(
            account_id=target.id, lifecycle=OperatorAccountLifecycle.ACTIVE
        ),
        "banned": OperatorAccountFilters(lifecycle=OperatorAccountLifecycle.BANNED),
        "deleted": OperatorAccountFilters(lifecycle=OperatorAccountLifecycle.DELETED),
        "time": OperatorAccountFilters(
            account_id=target.id,
            created_from=now - timedelta(days=1),
            created_before=now + timedelta(days=1),
        ),
    }
    search = SearchOperatorAccounts(
        uow(identity_engine), HASHER, HmacIntentFingerprinter(b"s" * 32), CODEC
    )
    page = await search(owner.credential, choices[kind])
    assert [row.account_id for row in page.accounts] == [target.id]
    detail = await ReadOperatorAccount(uow(identity_engine), HASHER)(owner.credential, target.id)
    assert detail is not None
    assert detail.profile is not None
    assert detail.photo is not None
    assert detail.goal is not None
    assert detail.account.display_name is not None
    assert detail.account.display_name.value == "Synthetic student"


async def test_role_revocation_waits_for_inspection_commit_then_denies_next_read(
    identity_engine: AsyncEngine,
) -> None:
    owner = await operator(identity_engine)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def pause(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        entered.set()
        await release.wait()

    async def revoke() -> None:
        async with async_sessionmaker(identity_engine).begin() as session:
            # Same account -> role order as the trusted writer contract; no session required.
            await session.execute(
                select(AccountRecord.id).where(AccountRecord.id == owner.id).with_for_update()
            )
            now = await session.scalar(select(func.clock_timestamp()))
            assert isinstance(now, datetime)
            session.add(
                OperatorAccessRevisionRecord(
                    account_id=owner.id, version=2, active=False, changed_at=now
                )
            )
            await session.flush()
            await session.execute(
                update(OperatorAccessRecord)
                .where(OperatorAccessRecord.account_id == owner.id)
                .values(current_version=2)
            )

    paused = SqlOperatorUnitOfWork(
        async_sessionmaker(identity_engine, expire_on_commit=False), pause
    )
    reading = asyncio.create_task(ReadOperatorAccount(paused, HASHER)(owner.credential, owner.id))
    revoking: asyncio.Task[None] | None = None
    try:
        await asyncio.wait_for(entered.wait(), 5)
        revoking = asyncio.create_task(revoke())
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(revoking), 0.1)
    finally:
        release.set()
        await asyncio.gather(reading, *(() if revoking is None else (revoking,)))
    assert reading.result() is not None
    with pytest.raises(OperatorAccessDeniedError):
        await ReadOperatorAccount(uow(identity_engine), HASHER)(owner.credential, owner.id)
    async with async_sessionmaker(identity_engine)() as session:
        audit = (await session.scalars(select(OperatorAuditRecord))).one()
        assert audit.operator_access_version == INITIAL_GRANT
        assert await session.get(OperatorAccessRevisionRecord, (owner.id, 1)) is not None
        assert await session.get(OperatorAccessRevisionRecord, (owner.id, 2)) is not None
