import asyncio
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.cursors import InvalidOperatorCursorError
from studymate.application.operator.identity_links import ReadOperatorIdentityLinks
from studymate.application.operator.identity_links_data import IDENTITY_LINKS_PAGE_SIZE
from studymate.domain.membership import GOOGLE_ISSUER
from studymate.domain.operator.audit import OperatorAudit
from studymate.infrastructure.operator.identity_links_cursors import (
    FernetOperatorIdentityLinksCursorCodec,
)
from studymate.infrastructure.operator.identity_links_transactions import (
    SqlOperatorIdentityLinksUnitOfWork,
)
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
    InstitutionalBindingRecord,
)
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.operator.test_reads import operator
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration
REMAINING_LINKS = 2
CODEC = FernetOperatorIdentityLinksCursorCodec.from_key(b"i" * 32)


def reader(engine: AsyncEngine) -> ReadOperatorIdentityLinks:
    return ReadOperatorIdentityLinks(
        SqlOperatorIdentityLinksUnitOfWork(
            async_sessionmaker(engine, expire_on_commit=False), record_operator_audit
        ),
        Sha256SessionHasher(),
        CODEC,
    )


async def retained_accounts(engine: AsyncEngine, count: int) -> tuple[UUID, ...]:
    ids = tuple(uuid4() for _ in range(count))
    async with async_sessionmaker(engine).begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        created = now - timedelta(days=2)
        retired = now - timedelta(days=1)
        session.add_all(
            AccountRecord(id=account_id, created_at=created, deleted_at=retired)
            for account_id in ids
        )
        await session.flush()
        for account_id in ids:
            session.add(
                ExternalIdentityRecord(
                    id=uuid4(),
                    account_id=account_id,
                    issuer=GOOGLE_ISSUER,
                    subject="retained-private-google",
                    created_at=created,
                    retired_at=retired,
                )
            )
            session.add(
                InstitutionalBindingRecord(
                    account_id=account_id,
                    email="retained.private@mail.apu.edu.my",
                    verified_at=created,
                    retired_at=retired,
                )
            )
    return ids


async def test_retained_claims_current_generation_and_direct_not_transitive_edges(
    identity_engine: AsyncEngine,
) -> None:
    viewer = await operator(identity_engine)
    old, related = await retained_accounts(identity_engine, 2)
    current = await actor(identity_engine, verified=False)
    email_only = await actor(identity_engine, verified=False)
    transitive = await actor(identity_engine, verified=False)
    async with async_sessionmaker(identity_engine).begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        session.add(
            ExternalIdentityRecord(
                id=uuid4(),
                account_id=current.id,
                issuer=GOOGLE_ISSUER,
                subject="retained-private-google",
                created_at=now,
            )
        )
        session.add(
            InstitutionalBindingRecord(
                account_id=email_only.id, email="retained.private@mail.apu.edu.my", verified_at=now
            )
        )
        # This second claim links to email_only, but does not match old's Google.
        await session.execute(
            update(AccountRecord).where(AccountRecord.id == transitive.id).values(deleted_at=now)
        )
        await session.flush()
        session.add(
            ExternalIdentityRecord(
                id=uuid4(),
                account_id=transitive.id,
                issuer=GOOGLE_ISSUER,
                subject="different-chain-google",
                created_at=now,
                retired_at=now,
            )
        )
        session.add(
            ExternalIdentityRecord(
                id=uuid4(),
                account_id=email_only.id,
                issuer=GOOGLE_ISSUER,
                subject="different-chain-google",
                created_at=now,
            )
        )
    page = await reader(identity_engine)(viewer.credential, old)
    assert page is not None
    assert page.target.deleted_at is not None
    assert page.target.google is not None
    assert page.target.google.retired_at is not None
    assert page.target.institutional is not None
    assert page.target.institutional.retired_at is not None
    links = {row.account.account_id: row for row in page.links}
    assert set(links) == {related, current.id, email_only.id}
    assert links[related].shared_google_claim
    assert links[related].shared_institutional_email
    assert links[current.id].shared_google_claim
    assert not links[current.id].shared_institutional_email
    assert not links[email_only.id].shared_google_claim
    assert links[email_only.id].shared_institutional_email
    assert "retained.private" not in repr(page)
    async with async_sessionmaker(identity_engine)() as session:
        audit = (await session.scalars(select(OperatorAuditRecord))).one()
        assert audit.requested_id == old
        assert audit.result_ids == [old]
        assert audit.query_fingerprint is None
        event = (await session.scalars(select(ProductEventRecord))).one()
        assert event.kind == "operator.inspected"
        assert event.operator_audit_id == audit.id


async def test_real_cursor_tied_order_new_account_exclusion_and_actor_scope(
    identity_engine: AsyncEngine,
) -> None:
    viewer = await operator(identity_engine)
    other = await operator(identity_engine)
    ids = await retained_accounts(identity_engine, 53)
    target = ids[0]
    usecase = reader(identity_engine)
    first = await usecase(viewer.credential, target)
    assert first is not None
    assert len(first.links) == IDENTITY_LINKS_PAGE_SIZE
    assert first.next_cursor is not None
    with pytest.raises(InvalidOperatorCursorError):
        await usecase(other.credential, target, first.next_cursor)
    with pytest.raises(InvalidOperatorCursorError):
        await usecase(viewer.credential, ids[1], first.next_cursor)
    newcomer = await actor(identity_engine, verified=False)
    async with async_sessionmaker(identity_engine).begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        session.add(
            ExternalIdentityRecord(
                id=uuid4(),
                account_id=newcomer.id,
                issuer=GOOGLE_ISSUER,
                subject="retained-private-google",
                created_at=now,
            )
        )
    second = await usecase(viewer.credential, target, first.next_cursor)
    assert second is not None
    assert len(second.links) == REMAINING_LINKS
    assert second.next_cursor is None
    actual = tuple(row.account.account_id for row in first.links + second.links)
    assert actual == tuple(sorted(ids[1:], reverse=True))
    assert newcomer.id not in actual
    assert second.as_of == first.as_of


@pytest.mark.parametrize("denial", ["absent", "revoked", "banned", "deleted"])
async def test_real_private_sources_never_escape_without_current_authority(
    identity_engine: AsyncEngine, denial: str
) -> None:
    viewer = (
        await actor(identity_engine)
        if denial == "absent"
        else await operator(identity_engine, active=denial != "revoked")
    )
    target = (await retained_accounts(identity_engine, 1))[0]
    if denial in {"banned", "deleted"}:
        async with async_sessionmaker(identity_engine).begin() as session:
            await session.execute(
                update(AccountRecord)
                .where(AccountRecord.id == viewer.id)
                .values(
                    banned_at=func.clock_timestamp() if denial == "banned" else None,
                    deleted_at=func.clock_timestamp() if denial == "deleted" else None,
                )
            )
    with pytest.raises(UnauthenticatedError if denial == "deleted" else OperatorAccessDeniedError):
        await reader(identity_engine)(viewer.credential, target)
    async with async_sessionmaker(identity_engine)() as session:
        assert tuple(await session.scalars(select(OperatorAuditRecord))) == ()


async def rejecting_recorder(session: AsyncSession, audit: OperatorAudit) -> None:
    await record_operator_audit(session, audit)
    raise RuntimeError("synthetic canonical failure")


async def test_actual_audit_rollback_and_missing_unlinked_account_outcomes(
    identity_engine: AsyncEngine,
) -> None:
    viewer = await operator(identity_engine)
    empty = await actor(identity_engine, verified=False)
    usecase = ReadOperatorIdentityLinks(
        SqlOperatorIdentityLinksUnitOfWork(
            async_sessionmaker(identity_engine, expire_on_commit=False), rejecting_recorder
        ),
        Sha256SessionHasher(),
        CODEC,
    )
    with pytest.raises(RuntimeError, match="synthetic canonical failure"):
        await usecase(viewer.credential, empty.id)
    async with async_sessionmaker(identity_engine)() as session:
        assert tuple(await session.scalars(select(OperatorAuditRecord))) == ()
        assert tuple(await session.scalars(select(ProductEventRecord))) == ()
    page = await reader(identity_engine)(viewer.credential, empty.id)
    assert page is not None
    assert page.links == ()
    assert page.target.google is None
    assert await reader(identity_engine)(viewer.credential, uuid4()) is None
    async with async_sessionmaker(identity_engine)() as session:
        assert {row.outcome for row in await session.scalars(select(OperatorAuditRecord))} == {
            "read",
            "not_found",
        }


async def cancelled_recorder(session: AsyncSession, audit: OperatorAudit) -> None:
    await record_operator_audit(session, audit)
    raise asyncio.CancelledError


async def test_cancellation_propagates_and_rolls_back_private_inspection(
    identity_engine: AsyncEngine,
) -> None:
    viewer = await operator(identity_engine)
    target = (await retained_accounts(identity_engine, 1))[0]
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    read = ReadOperatorIdentityLinks(
        SqlOperatorIdentityLinksUnitOfWork(sessions, cancelled_recorder),
        Sha256SessionHasher(),
        CODEC,
    )
    with pytest.raises(asyncio.CancelledError):
        await read(viewer.credential, target)
    async with sessions() as session:
        assert tuple(await session.scalars(select(OperatorAuditRecord))) == ()
        assert tuple(await session.scalars(select(ProductEventRecord))) == ()
