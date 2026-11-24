"""Seeded native migration/purge facts, not an old-binary rollback allowlist."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.identity.native_login import (
    BindNativeCallback,
    ExchangeNativeAttempt,
    NativeLoginRejectedError,
    RegisterNativeAttempt,
    proof_challenge,
)
from studymate.application.identity.sessions import (
    ReadIdentity,
    SessionCredential,
    UnauthenticatedError,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityUnitOfWork
from studymate.infrastructure.persistence.native_login import (
    NativeAttemptRecord,
    SqlNativeUnitOfWork,
)
from studymate.infrastructure.security.login_vault import AeadLoginVault
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.migrations import migrate

pytestmark = pytest.mark.integration
PREVIOUS = "0060_report_triage"
NATIVE = "0061_native_login"
VERIFIER = "A" * 43
HASHER = Sha256SessionHasher()
VAULT = AeadLoginVault(bytes(range(32)))
LEGACY_SESSION_COUNT = 2


@dataclass(frozen=True, slots=True)
class Seed:
    account_id: UUID
    source_id: UUID
    unrelated_id: UUID
    source: SessionCredential = field(repr=False)
    unrelated: SessionCredential = field(repr=False)


async def upgrade(engine: AsyncEngine, revision: str) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(migrate, revision)


def downgrade_to_previous(connection: Connection) -> None:
    config = Config("alembic.ini")
    config.attributes["connection"] = connection
    command.downgrade(config, PREVIOUS)


async def assert_revision(engine: AsyncEngine, expected: str) -> None:
    async with engine.connect() as connection:
        actual: object = (
            await connection.execute(text("SELECT version_num FROM alembic_version"))
        ).scalar_one()
        assert actual == expected


async def legacy_seed(engine: AsyncEngine) -> Seed:
    await upgrade(engine, PREVIOUS)
    seed = Seed(
        uuid4(),
        uuid4(),
        uuid4(),
        await VAULT.session_credential(),
        await VAULT.session_credential(),
    )
    now = datetime.now(UTC)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions.begin() as session:
        session.add(AccountRecord(id=seed.account_id, created_at=now - timedelta(days=1)))
        await session.flush()
        for identifier, credential in [
            (seed.source_id, seed.source),
            (seed.unrelated_id, seed.unrelated),
        ]:
            session.add(
                SessionRecord(
                    id=identifier,
                    account_id=seed.account_id,
                    secret_digest=await HASHER.digest(credential),
                    issued_at=now - timedelta(minutes=20),
                    expires_at=now + timedelta(days=1),
                )
            )
    return seed


async def test_seeded_0060_upgrade_retains_legacy_sessions_and_native_constraints(
    engine: AsyncEngine,
) -> None:
    seed = await legacy_seed(engine)
    await assert_revision(engine, PREVIOUS)
    statement = select(
        SessionRecord.id,
        SessionRecord.account_id,
        SessionRecord.secret_digest,
        SessionRecord.issued_at,
        SessionRecord.expires_at,
        SessionRecord.revoked_at,
    ).order_by(SessionRecord.id)
    async with engine.connect() as connection:
        before = (await connection.execute(statement)).all()
        assert (
            await connection.execute(text("SELECT to_regclass('native_login_attempts') IS NULL"))
        ).scalar_one() is True
    await upgrade(engine, NATIVE)
    await assert_revision(engine, NATIVE)
    async with engine.connect() as connection:
        assert (await connection.execute(statement)).all() == before
        kinds = (
            (
                await connection.execute(
                    text(
                        "SELECT contype::text FROM pg_constraint "
                        "WHERE conrelid='native_login_attempts'::regclass"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert sorted(kinds) == ["c", "c", "c", "c", "c", "f", "p", "u", "u"]
        assert (
            await connection.execute(
                text(
                    "SELECT confdeltype::text FROM pg_constraint "
                    "WHERE conrelid='native_login_attempts'::regclass "
                    "AND contype='f' AND confrelid='sessions'::regclass"
                )
            )
        ).scalar_one() == "r"
        assert (
            await connection.execute(
                text("SELECT to_regclass('ix_native_login_attempts_expires_at') IS NOT NULL")
            )
        ).scalar_one() is True
    reader = ReadIdentity(
        SqlIdentityUnitOfWork(async_sessionmaker(engine, expire_on_commit=False)), HASHER
    )
    assert (await reader(seed.source)).session.id == seed.source_id
    assert (await reader(seed.unrelated)).session.id == seed.unrelated_id


@pytest.mark.parametrize("consumed", [False, True], ids=["expired-pending", "expired-consumed"])
async def test_retained_attempt_blocks_expired_session_purge(
    engine: AsyncEngine, consumed: bool
) -> None:
    seed = await legacy_seed(engine)
    await upgrade(engine, NATIVE)
    now = datetime.now(UTC)
    created = now - timedelta(minutes=10)
    expired = now - timedelta(minutes=1)
    attempt_id = uuid4()
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions.begin() as session:
        await session.execute(update(SessionRecord).values(expires_at=expired))
        session.add(
            NativeAttemptRecord(
                id=attempt_id,
                challenge=proof_challenge(VERIFIER),
                browser_digest=uuid4().bytes * 2,
                created_at=created,
                expires_at=expired,
                source_digest=await HASHER.digest(seed.source),
                consumed_at=created + timedelta(seconds=30) if consumed else None,
            )
        )
    with pytest.raises(IntegrityError) as rejected:
        async with sessions.begin() as session:
            await session.execute(delete(SessionRecord).where(SessionRecord.expires_at < now))
    assert getattr(rejected.value.orig, "sqlstate", None) == "23503"
    async with sessions.begin() as session:
        assert (
            await session.scalar(select(func.count()).select_from(SessionRecord))
            == LEGACY_SESSION_COUNT
        )
        await session.execute(delete(SessionRecord).where(SessionRecord.id == seed.unrelated_id))
    async with sessions.begin() as session:
        assert await session.get(SessionRecord, seed.source_id) is not None
        # Explicit test-only ordering, NOT a new production purge/erasure policy.
        await session.execute(
            delete(NativeAttemptRecord).where(NativeAttemptRecord.id == attempt_id)
        )
        await session.execute(delete(SessionRecord).where(SessionRecord.id == seed.source_id))
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(SessionRecord)) == 0


async def test_quiesced_downgrade_does_not_restore_provisional_or_erase_issued_session(
    engine: AsyncEngine,
) -> None:
    seed = await legacy_seed(engine)
    await upgrade(engine, NATIVE)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    uow = SqlNativeUnitOfWork(sessions)
    browser = await VAULT.session_credential()
    attempt_id = uuid4()
    await RegisterNativeAttempt(uow, HASHER)(attempt_id, proof_challenge(VERIFIER), browser)
    assert await BindNativeCallback(uow, HASHER)(browser, seed.source)
    issued = await ExchangeNativeAttempt(uow, HASHER, VAULT)(attempt_id, VERIFIER)
    reader = ReadIdentity(SqlIdentityUnitOfWork(sessions), HASHER)
    native_identity = await reader(issued)
    with pytest.raises(UnauthenticatedError):
        await reader(seed.source)
    async with engine.begin() as connection:
        await connection.run_sync(downgrade_to_previous)
    await assert_revision(engine, PREVIOUS)
    async with engine.connect() as connection:
        assert (
            await connection.execute(text("SELECT to_regclass('native_login_attempts') IS NULL"))
        ).scalar_one() is True
    assert (await reader(issued)).session.id == native_identity.session.id
    assert (await reader(seed.unrelated)).session.id == seed.unrelated_id
    with pytest.raises(UnauthenticatedError):
        await reader(seed.source)
    await upgrade(engine, NATIVE)
    await assert_revision(engine, NATIVE)
    with pytest.raises(NativeLoginRejectedError):
        await ExchangeNativeAttempt(uow, HASHER, VAULT)(attempt_id, VERIFIER)
    assert (await reader(issued)).session.id == native_identity.session.id
