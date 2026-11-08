import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import String, cast, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from studymate.application.idempotency import IntentKey
from studymate.application.identity.email_delivery import (
    DeliverVerificationEmail,
    DeliveryResolution,
    DeliveryStatus,
    DeliveryStep,
    TransientEmailError,
    VerificationEmail,
)
from studymate.application.identity.email_verification import (
    StartChallengeCommand,
    StartEmailChallenge,
)
from studymate.application.identity.sessions import ReadIdentity, SessionCredential
from studymate.domain.identity import StudentEmail
from studymate.infrastructure.persistence.email_delivery import SqlEmailWorkerUnitOfWork
from studymate.infrastructure.persistence.email_models import (
    EmailChallengeRecord,
    EmailDeliveryRecord,
)
from studymate.infrastructure.persistence.email_verification import SqlEmailUnitOfWork
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityUnitOfWork
from studymate.infrastructure.security.email_vault import AeadEmailVault
from studymate.infrastructure.security.session_digest import Sha256SessionHasher

pytestmark = pytest.mark.integration
MAX_ATTEMPTS = 3


def vault() -> AeadEmailVault:
    return AeadEmailVault(bytes(range(32)), bytes(range(32, 64)))


async def queued(engine: AsyncEngine) -> SessionCredential:
    credential = SessionCredential("x" * 43)
    now = datetime.now(UTC)
    account_id = uuid4()
    async with async_sessionmaker(engine).begin() as session:
        session.add(AccountRecord(id=account_id, created_at=now))
        await session.flush()
        session.add(
            SessionRecord(
                id=uuid4(),
                account_id=account_id,
                issued_at=now - timedelta(seconds=1),
                expires_at=now + timedelta(days=7),
                secret_digest=await Sha256SessionHasher().digest(credential),
            )
        )
    await StartEmailChallenge(
        SqlEmailUnitOfWork(async_sessionmaker(engine)), Sha256SessionHasher(), vault()
    )(
        StartChallengeCommand(
            credential, StudentEmail("tp@mail.apu.edu.my"), IntentKey(str(uuid4())), bytes(32)
        ),
    )
    return credential


class Sender:
    def __init__(self) -> None:
        self.messages: list[UUID] = []
        self.transient = False
        self.wait = False
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def send(self, message: VerificationEmail, delivery_id: UUID) -> None:
        assert message.email == StudentEmail("tp@mail.apu.edu.my")
        assert message.code.value
        self.messages.append(delivery_id)
        self.started.set()
        if self.wait:
            await self.release.wait()
        if self.transient:
            raise TransientEmailError


async def test_worker_commits_ack_erases_envelope_and_does_not_redeliver(
    identity_engine: AsyncEngine,
) -> None:
    await queued(identity_engine)
    sender = Sender()
    uow = SqlEmailWorkerUnitOfWork(async_sessionmaker(identity_engine))
    worker = DeliverVerificationEmail(uow, sender, vault())
    assert await worker() == DeliveryStep.DELIVERED
    assert await worker() == DeliveryStep.IDLE
    async with async_sessionmaker(identity_engine)() as session:
        stored = (await session.scalars(select(EmailDeliveryRecord))).one()
        assert stored.status == "delivered"
        assert stored.sealed_envelope is None
        assert stored.delivered_at is not None
        assert stored.attempts == 1
    assert len(sender.messages) == 1


async def test_transient_failures_retry_same_delivery_and_exhaust_budget(
    identity_engine: AsyncEngine,
) -> None:
    await queued(identity_engine)
    sender = Sender()
    sender.transient = True
    worker = DeliverVerificationEmail(
        SqlEmailWorkerUnitOfWork(async_sessionmaker(identity_engine)), sender, vault()
    )
    for attempt in range(1, MAX_ATTEMPTS + 1):
        assert await worker() == (
            DeliveryStep.FAILED if attempt == MAX_ATTEMPTS else DeliveryStep.RETRY
        )
        async with async_sessionmaker(identity_engine).begin() as session:
            await session.execute(
                update(EmailDeliveryRecord).values(
                    due_at=func.clock_timestamp() - timedelta(seconds=1)
                )
            )
    assert await worker() == DeliveryStep.IDLE
    assert len(set(sender.messages)) == 1
    async with async_sessionmaker(identity_engine)() as session:
        stored = (await session.scalars(select(EmailDeliveryRecord))).one()
        assert stored.status == "failed"
        assert stored.sealed_envelope is None
        assert stored.last_error == "provider_unavailable"
        assert stored.attempts == MAX_ATTEMPTS


async def test_expired_lease_reclaims_and_stale_ack_cannot_overwrite(
    identity_engine: AsyncEngine,
) -> None:
    await queued(identity_engine)
    uow = SqlEmailWorkerUnitOfWork(async_sessionmaker(identity_engine))
    async with uow.transaction() as transaction:
        now = await transaction.now()
        first = await transaction.claim(now, now + timedelta(seconds=30))
    assert first is not None
    async with async_sessionmaker(identity_engine).begin() as session:
        await session.execute(
            update(EmailDeliveryRecord).values(
                lease_until=func.clock_timestamp() - timedelta(seconds=1)
            )
        )
    async with uow.transaction() as transaction:
        now = await transaction.now()
        second = await transaction.claim(now, now + timedelta(seconds=30))
    assert second is not None
    assert second.generation > first.generation
    async with uow.transaction() as transaction:
        now = await transaction.now()
        assert not await transaction.finish(
            first, DeliveryResolution(DeliveryStatus.DELIVERED), now
        )
        assert await transaction.finish(second, DeliveryResolution(DeliveryStatus.DELIVERED), now)


async def test_exhausted_crashed_lease_is_cleaned_without_provider_call(
    identity_engine: AsyncEngine,
) -> None:
    await queued(identity_engine)
    uow = SqlEmailWorkerUnitOfWork(async_sessionmaker(identity_engine))
    for _ in range(MAX_ATTEMPTS):
        async with uow.transaction() as transaction:
            now = await transaction.now()
            assert await transaction.claim(now, now + timedelta(seconds=30)) is not None
        async with async_sessionmaker(identity_engine).begin() as session:
            await session.execute(
                update(EmailDeliveryRecord).values(
                    lease_until=func.clock_timestamp() - timedelta(seconds=1)
                )
            )
    sender = Sender()
    assert await DeliverVerificationEmail(uow, sender, vault())() == DeliveryStep.IDLE
    assert sender.messages == []
    async with async_sessionmaker(identity_engine)() as session:
        stored = (await session.scalars(select(EmailDeliveryRecord))).one()
        assert stored.status == "failed"
        assert stored.sealed_envelope is None


async def test_expired_code_erases_digest_and_delivery_secret(identity_engine: AsyncEngine) -> None:
    await queued(identity_engine)
    async with async_sessionmaker(identity_engine).begin() as session:
        await session.execute(
            update(EmailChallengeRecord).values(
                created_at=func.clock_timestamp() - timedelta(minutes=11),
                resend_at=func.clock_timestamp() - timedelta(minutes=10),
                expires_at=func.clock_timestamp() - timedelta(seconds=1),
            )
        )
    sender = Sender()
    uow = SqlEmailWorkerUnitOfWork(async_sessionmaker(identity_engine))
    assert await DeliverVerificationEmail(uow, sender, vault())() == DeliveryStep.IDLE
    assert sender.messages == []
    async with async_sessionmaker(identity_engine)() as session:
        stored = (await session.scalars(select(EmailDeliveryRecord))).one()
        assert stored.status == "cancelled"
        assert stored.sealed_envelope is None
        challenge = (await session.scalars(select(EmailChallengeRecord))).one()
        assert challenge.code_digest is None


async def test_slow_provider_does_not_hold_sql_connection_or_account_lock(
    identity_engine: AsyncEngine,
) -> None:
    credential = await queued(identity_engine)
    async with identity_engine.connect() as connection:
        schema = await connection.scalar(select(cast(func.current_schema(), String)))
    assert schema is not None
    one_connection = create_async_engine(
        identity_engine.url,
        connect_args={"server_settings": {"search_path": schema}},
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.2,
    )
    sender = Sender()
    sender.wait = True
    sessions = async_sessionmaker(one_connection)
    task = asyncio.create_task(
        DeliverVerificationEmail(SqlEmailWorkerUnitOfWork(sessions), sender, vault())()
    )
    try:
        await asyncio.wait_for(sender.started.wait(), timeout=2)
        identity = await asyncio.wait_for(
            ReadIdentity(SqlIdentityUnitOfWork(sessions), Sha256SessionHasher())(credential),
            timeout=1,
        )
        assert identity.session.is_active(datetime.now(UTC))
    finally:
        sender.release.set()
        await task
        await one_connection.dispose()
