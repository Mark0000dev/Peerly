"""Retained business fixtures on real migrations, never an alternate schema."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.domain.membership import GOOGLE_ISSUER
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
    InstitutionalBindingRecord,
    SessionRecord,
)
from tests.integration.operator.test_reads import operator

EMAIL = "retained-recreation@mail.apu.edu.my"


@dataclass(frozen=True, slots=True)
class RetainedClaims:
    account_id: UUID
    identity_id: UUID
    subject: str
    session_id: UUID
    retired_at: datetime


async def deleted_claims(engine: AsyncEngine) -> RetainedClaims:
    # Existing fixture deliberately supplies a real original Google FK + operator
    # grant and session. The test must preserve all of these historical references.
    owner = await operator(engine)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions.begin() as session:
        at = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(at, datetime)
        identity = (
            await session.scalars(
                select(ExternalIdentityRecord).where(ExternalIdentityRecord.account_id == owner.id)
            )
        ).one()
        original_session = (
            await session.scalars(select(SessionRecord).where(SessionRecord.account_id == owner.id))
        ).one()
        await session.execute(
            update(AccountRecord).where(AccountRecord.id == owner.id).values(deleted_at=at)
        )
        identity.retired_at = at
        session.add(
            InstitutionalBindingRecord(
                account_id=owner.id, email=EMAIL, verified_at=at, retired_at=at
            )
        )
        await session.execute(
            update(SessionRecord).where(SessionRecord.account_id == owner.id).values(revoked_at=at)
        )
        return RetainedClaims(owner.id, identity.id, identity.subject, original_session.id, at)


async def fresh_account(engine: AsyncEngine) -> UUID:
    owner = uuid4()
    async with async_sessionmaker(engine).begin() as session:
        at = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(at, datetime)
        session.add(AccountRecord(id=owner, created_at=at))
    return owner


def google_claim(owner: UUID, subject: str, at: datetime) -> ExternalIdentityRecord:
    return ExternalIdentityRecord(
        id=uuid4(),
        account_id=owner,
        issuer=GOOGLE_ISSUER,
        subject=subject,
        created_at=at,
        retired_at=None,
    )
