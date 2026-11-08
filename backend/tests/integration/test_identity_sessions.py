import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.identity.sessions import (
    Logout,
    ReadIdentity,
    SessionCredential,
    UnauthenticatedError,
)
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
    SessionRecord,
)
from studymate.infrastructure.persistence.identity_sessions import (
    SqlIdentityTransaction,
    SqlIdentityUnitOfWork,
)
from studymate.infrastructure.security.session_digest import Sha256SessionHasher

DIGEST_BYTES = 32
pytestmark = pytest.mark.integration


async def seed_session(engine: AsyncEngine, *, verified: bool) -> SessionCredential:
    credential = SessionCredential("c" * 43)
    account_id = uuid4()
    now = datetime.now(UTC)
    async with async_sessionmaker(engine).begin() as session:
        session.add(AccountRecord(id=account_id, created_at=now))
        await session.flush()
        session.add(
            SessionRecord(
                id=uuid4(),
                account_id=account_id,
                secret_digest=await Sha256SessionHasher().digest(credential),
                issued_at=now - timedelta(seconds=1),
                expires_at=now + timedelta(days=7),
            )
        )
        if verified:
            session.add(
                InstitutionalBindingRecord(
                    account_id=account_id,
                    email="tp@mail.apu.edu.my",
                    verified_at=now,
                )
            )
    return credential


@pytest.mark.parametrize("verified", [True, False])
async def test_identity_is_loaded_from_business_storage_not_claims(
    identity_engine: AsyncEngine,
    verified: bool,
) -> None:
    credential = await seed_session(identity_engine, verified=verified)
    uow = SqlIdentityUnitOfWork(async_sessionmaker(identity_engine, expire_on_commit=False))
    result = await ReadIdentity(uow, Sha256SessionHasher())(credential)
    assert (result.membership is not None) == verified
    assert not result.banned
    if result.membership is not None:
        assert result.membership.email.value == "tp@mail.apu.edu.my"
    assert result.session.is_active(datetime.now(UTC))


async def test_unknown_session_is_unavailable(identity_engine: AsyncEngine) -> None:
    uow = SqlIdentityUnitOfWork(async_sessionmaker(identity_engine, expire_on_commit=False))
    with pytest.raises(UnauthenticatedError):
        await ReadIdentity(uow, Sha256SessionHasher())(SessionCredential("d" * 43))
    await Logout(uow, Sha256SessionHasher())(SessionCredential("d" * 43))


async def test_concurrent_logout_is_idempotent_and_authoritative(
    identity_engine: AsyncEngine,
) -> None:
    credential = await seed_session(identity_engine, verified=True)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    uow = SqlIdentityUnitOfWork(sessions)
    logout = Logout(uow, Sha256SessionHasher())
    await asyncio.gather(logout(credential), logout(credential))
    with pytest.raises(UnauthenticatedError):
        await ReadIdentity(uow, Sha256SessionHasher())(credential)
    async with sessions() as session:
        stored = (await session.scalars(select(SessionRecord))).one()
        assert stored.revoked_at is not None
        assert len(stored.secret_digest) == DIGEST_BYTES
        binding = (await session.scalars(select(InstitutionalBindingRecord))).one()
        assert binding.revoked_at is None


async def test_uow_rolls_back_revocation_on_failure(identity_engine: AsyncEngine) -> None:
    credential = await seed_session(identity_engine, verified=False)
    uow = SqlIdentityUnitOfWork(async_sessionmaker(identity_engine, expire_on_commit=False))

    async def failed_operation() -> None:
        async with uow.transaction() as transaction:
            identity = await transaction.lock_identity(
                await Sha256SessionHasher().digest(credential)
            )
            assert identity is not None
            await transaction.revoke_session(identity.session.id, await transaction.now())
            raise RuntimeError("controlled transaction failure")

    with pytest.raises(RuntimeError, match="controlled"):
        await failed_operation()
    assert (await ReadIdentity(uow, Sha256SessionHasher())(credential)).session.revoked_at is None


async def test_reciprocal_peer_identity_locks_complete_without_deadlock(
    identity_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    first_id, second_id = uuid4(), uuid4()
    first_credential = SessionCredential("e" * 43)
    second_credential = SessionCredential("f" * 43)
    hasher = Sha256SessionHasher()
    now = datetime.now(UTC)
    async with sessions.begin() as session:
        session.add_all(
            AccountRecord(id=account_id, created_at=now) for account_id in (first_id, second_id)
        )
        await session.flush()
        for account_id, credential in (
            (first_id, first_credential),
            (second_id, second_credential),
        ):
            session.add(
                SessionRecord(
                    id=uuid4(),
                    account_id=account_id,
                    secret_digest=await hasher.digest(credential),
                    issued_at=now,
                    expires_at=now + timedelta(days=1),
                )
            )
    start = asyncio.Event()

    async def lock_peer(credential: SessionCredential, peer_id: UUID) -> UUID:
        await start.wait()
        async with sessions.begin() as session:
            transaction = SqlIdentityTransaction(session)
            identity = await transaction.lock_identity_for_peer(
                await hasher.digest(credential), peer_id
            )
            assert identity is not None
            # Both account rows remain locked until this actual transaction completes.
            await asyncio.sleep(0)
            return identity.session.account_id

    first = asyncio.create_task(lock_peer(first_credential, second_id))
    second = asyncio.create_task(lock_peer(second_credential, first_id))
    start.set()
    assert set(await asyncio.wait_for(asyncio.gather(first, second), timeout=5)) == {
        first_id,
        second_id,
    }
