import asyncio
from datetime import datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.domain.membership import GOOGLE_ISSUER
from studymate.infrastructure.operator.models import (
    OperatorAccessRecord,
    OperatorAccessRevisionRecord,
)
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
    InstitutionalBindingRecord,
    SessionRecord,
)
from tests.integration.identity_recreation.fixtures import (
    EMAIL,
    deleted_claims,
    fresh_account,
    google_claim,
)

pytestmark = pytest.mark.integration
EXPECTED_LINEAGES = 2


async def test_new_account_claims_preserve_old_google_mailbox_session_and_operator_foreign_keys(
    identity_engine: AsyncEngine,
) -> None:
    old = await deleted_claims(identity_engine)
    new_owner = await fresh_account(identity_engine)
    assert new_owner != old.account_id
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        at = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(at, datetime)
        session.add(google_claim(new_owner, old.subject, at))
        session.add(
            InstitutionalBindingRecord(
                account_id=new_owner, email=EMAIL, verified_at=at, retired_at=None
            )
        )
    async with sessions() as session:
        identities = (
            await session.scalars(
                select(ExternalIdentityRecord).where(
                    ExternalIdentityRecord.issuer == GOOGLE_ISSUER,
                    ExternalIdentityRecord.subject == old.subject,
                )
            )
        ).all()
        assert len(identities) == EXPECTED_LINEAGES
        historical_identity = await session.get(ExternalIdentityRecord, old.identity_id)
        assert historical_identity is not None
        assert historical_identity.account_id == old.account_id
        assert historical_identity.issuer == GOOGLE_ISSUER
        assert historical_identity.subject == old.subject
        assert historical_identity.retired_at == old.retired_at
        active_identity = (
            await session.scalars(
                select(ExternalIdentityRecord).where(
                    ExternalIdentityRecord.subject == old.subject,
                    ExternalIdentityRecord.retired_at.is_(None),
                )
            )
        ).one()
        assert active_identity.account_id == new_owner
        historical_binding = await session.get(InstitutionalBindingRecord, old.account_id)
        assert historical_binding is not None
        assert historical_binding.email == EMAIL
        assert historical_binding.retired_at == old.retired_at
        active_binding = await session.get(InstitutionalBindingRecord, new_owner)
        assert active_binding is not None
        assert active_binding.email == EMAIL
        assert active_binding.retired_at is None
        original_session = await session.get(SessionRecord, old.session_id)
        assert original_session is not None
        assert original_session.account_id == old.account_id
        assert original_session.revoked_at == old.retired_at
        assert await session.get(OperatorAccessRecord, old.account_id) is not None
        assert await session.get(OperatorAccessRevisionRecord, (old.account_id, 1)) is not None
        original_account = await session.get(AccountRecord, old.account_id)
        assert original_account is not None
        assert original_account.deleted_at == old.retired_at
        recreated = await session.get(AccountRecord, new_owner)
        assert recreated is not None
        assert recreated.deleted_at is None
        assert recreated.banned_at is None


@pytest.mark.parametrize("kind", ["google", "mailbox"])
async def test_only_one_concurrent_active_claim_commits_while_history_remains_unchanged(
    identity_engine: AsyncEngine, kind: str
) -> None:
    old = await deleted_claims(identity_engine)
    owners = (await fresh_account(identity_engine), await fresh_account(identity_engine))
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    barrier = asyncio.Barrier(len(owners))

    async def claim(owner: UUID) -> bool:
        try:
            async with sessions.begin() as session:
                at = await session.scalar(select(func.clock_timestamp()))
                assert isinstance(at, datetime)
                await barrier.wait()
                if kind == "google":
                    session.add(google_claim(owner, old.subject, at))
                else:
                    session.add(
                        InstitutionalBindingRecord(
                            account_id=owner, email=EMAIL, verified_at=at, retired_at=None
                        )
                    )
                await session.flush()
            return True
        except IntegrityError:
            return False

    outcomes = await asyncio.gather(*(claim(owner) for owner in owners))
    assert outcomes.count(True) == 1
    assert outcomes.count(False) == 1
    async with sessions() as session:
        if kind == "google":
            active_owners = tuple(
                await session.scalars(
                    select(ExternalIdentityRecord.account_id).where(
                        ExternalIdentityRecord.subject == old.subject,
                        ExternalIdentityRecord.retired_at.is_(None),
                    )
                )
            )
        else:
            active_owners = tuple(
                await session.scalars(
                    select(InstitutionalBindingRecord.account_id).where(
                        InstitutionalBindingRecord.email == EMAIL,
                        InstitutionalBindingRecord.retired_at.is_(None),
                    )
                )
            )
        assert len(active_owners) == 1
        assert active_owners[0] in owners
        original = await session.get(ExternalIdentityRecord, old.identity_id)
        binding = await session.get(InstitutionalBindingRecord, old.account_id)
        assert original is not None
        assert binding is not None
        assert original.retired_at == old.retired_at
        assert binding.retired_at == old.retired_at


@pytest.mark.parametrize("banned", [False, True])
async def test_revocation_without_deletion_keeps_mailbox_claim_reserved(
    identity_engine: AsyncEngine, banned: bool
) -> None:
    owner = await fresh_account(identity_engine)
    challenger = await fresh_account(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        at = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(at, datetime)
        session.add(
            InstitutionalBindingRecord(
                account_id=owner, email=EMAIL, verified_at=at, revoked_at=at, retired_at=None
            )
        )
        if banned:
            await session.execute(
                update(AccountRecord).where(AccountRecord.id == owner).values(banned_at=at)
            )
    async with sessions() as session:
        session.add(
            InstitutionalBindingRecord(
                account_id=challenger, email=EMAIL, verified_at=at, retired_at=None
            )
        )
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()
    async with sessions() as session:
        binding = await session.get(InstitutionalBindingRecord, owner)
        assert binding is not None
        assert binding.retired_at is None
        assert binding.revoked_at == at
        assert await session.get(InstitutionalBindingRecord, challenger) is None


async def test_original_account_google_uniqueness_and_history_foreign_keys_are_still_enforced(
    identity_engine: AsyncEngine,
) -> None:
    old = await deleted_claims(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions() as session:
        session.add(google_claim(old.account_id, "different-subject", old.retired_at))
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()
    async with sessions() as session:
        identity = await session.get(ExternalIdentityRecord, old.identity_id)
        assert identity is not None
        await session.delete(identity)
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()


@pytest.mark.parametrize("kind", ["google", "mailbox"])
@pytest.mark.parametrize("source", ["live_account", "wrong_deleted_timestamp"])
async def test_retirement_requires_the_actual_account_deletion_source(
    identity_engine: AsyncEngine,
    kind: str,
    source: str,
) -> None:
    owner = await fresh_account(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    with pytest.raises(IntegrityError):
        await invalid_retirement(identity_engine, owner, kind, source)
    async with sessions() as session:
        assert await session.get(InstitutionalBindingRecord, owner) is None
        assert not tuple(
            await session.scalars(
                select(ExternalIdentityRecord).where(ExternalIdentityRecord.account_id == owner)
            )
        )


async def invalid_retirement(engine: AsyncEngine, owner: UUID, kind: str, source: str) -> None:
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions.begin() as session:
        at = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(at, datetime)
        retirement = at
        if source == "wrong_deleted_timestamp":
            await session.execute(
                update(AccountRecord).where(AccountRecord.id == owner).values(deleted_at=at)
            )
            retirement = at + timedelta(microseconds=1)
        if kind == "google":
            claim = google_claim(owner, "retirement-requires-actual-deletion", at)
            claim.retired_at = retirement
            session.add(claim)
        else:
            session.add(
                InstitutionalBindingRecord(
                    account_id=owner, email=EMAIL, verified_at=at, retired_at=retirement
                )
            )
        await session.flush()
