"""Retired email association is not authority: fresh proof and retained bans apply."""

from datetime import datetime

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.identity.email_verification import VerificationOutcome
from studymate.application.identity.sessions import ReadIdentity
from studymate.infrastructure.persistence.identity_claims import retire_deleted_claims
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
)
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityUnitOfWork
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.test_email_verification import (
    EMAIL,
    actor,
    code_for,
    services,
    start_command,
    verify_command,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("banned", [False, True])
async def test_fresh_mail_proof_reuses_only_deleted_unbanned_address(
    identity_engine: AsyncEngine, banned: bool
) -> None:
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    read = ReadIdentity(SqlIdentityUnitOfWork(sessions), Sha256SessionHasher())
    previous = await actor(identity_engine)
    old_id = (await read(previous)).session.account_id
    async with sessions.begin() as session:
        at = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(at, datetime)
        session.add(
            InstitutionalBindingRecord(account_id=old_id, email=EMAIL.value, verified_at=at)
        )
        await session.flush()
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == old_id)
            .values(deleted_at=at, banned_at=at if banned else None)
        )
        await retire_deleted_claims(session, old_id)
    current = await actor(identity_engine)
    assert (await read(current)).membership is None
    start, verify = services(identity_engine)
    challenge = await start(start_command(current))
    result = await verify(
        verify_command(current, challenge, await code_for(identity_engine, challenge.id))
    )
    expected = VerificationOutcome.SUPPORT_REQUIRED if banned else VerificationOutcome.VERIFIED
    assert result.outcome == expected
    identity = await read(current)
    assert (identity.membership is not None) is (not banned)
    async with sessions() as session:
        original = await session.get(InstitutionalBindingRecord, old_id)
        assert original is not None
        assert original.email == EMAIL.value
        assert original.retired_at is not None
