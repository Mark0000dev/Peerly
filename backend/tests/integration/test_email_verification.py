import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.email_verification import (
    ChallengeCreated,
    EmailActionDeniedError,
    EmailChallengeUnavailableError,
    EmailPolicy,
    EmailRateLimitedError,
    ReadChallengeCommand,
    ReadEmailChallenge,
    StartChallengeCommand,
    StartEmailChallenge,
    VerificationCode,
    VerificationOutcome,
    VerifyChallengeCommand,
    VerifyStudentEmail,
)
from studymate.application.identity.sessions import (
    Logout,
    ReadIdentity,
    SessionCredential,
    UnauthenticatedError,
)
from studymate.domain.identity import StudentEmail
from studymate.infrastructure.persistence.email_models import (
    EmailChallengeRecord,
    EmailDeliveryRecord,
)
from studymate.infrastructure.persistence.email_verification import SqlEmailUnitOfWork
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
    SessionRecord,
)
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityUnitOfWork
from studymate.infrastructure.security.email_vault import AeadEmailVault
from studymate.infrastructure.security.session_digest import Sha256SessionHasher

pytestmark = pytest.mark.integration
EMAIL = StudentEmail("tp@mail.apu.edu.my")
SOURCE = bytes(32)
LAST_WRONG_ATTEMPT = 5
DEFAULT_POLICY = EmailPolicy()


def vault() -> AeadEmailVault:
    return AeadEmailVault(bytes(range(32)), bytes(range(32, 64)))


def services(
    engine: AsyncEngine, policy: EmailPolicy = DEFAULT_POLICY
) -> tuple[StartEmailChallenge, VerifyStudentEmail]:
    uow = SqlEmailUnitOfWork(async_sessionmaker(engine, expire_on_commit=False))
    hasher = Sha256SessionHasher()
    return StartEmailChallenge(uow, hasher, vault(), policy), VerifyStudentEmail(
        uow, hasher, vault()
    )


async def actor(engine: AsyncEngine, account_id: UUID | None = None) -> SessionCredential:
    credential = SessionCredential(uuid4().hex + uuid4().hex[:11])
    now = datetime.now(UTC)
    async with async_sessionmaker(engine).begin() as session:
        if account_id is None:
            account_id = uuid4()
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
    return credential


def start_command(
    credential: SessionCredential, email: StudentEmail = EMAIL
) -> StartChallengeCommand:
    return StartChallengeCommand(credential, email, IntentKey(str(uuid4())), SOURCE)


async def code_for(engine: AsyncEngine, challenge_id: UUID) -> VerificationCode:
    async with async_sessionmaker(engine)() as session:
        delivery = (
            await session.scalars(
                select(EmailDeliveryRecord).where(EmailDeliveryRecord.challenge_id == challenge_id)
            )
        ).one()
        assert delivery.status == "queued"
        assert delivery.sealed_envelope is not None
        return (await vault().open_delivery(challenge_id, delivery.sealed_envelope)).code


def verify_command(
    credential: SessionCredential, challenge: ChallengeCreated, code: VerificationCode
) -> VerifyChallengeCommand:
    return VerifyChallengeCommand(credential, challenge.id, code, IntentKey(str(uuid4())))


async def allow_resend(engine: AsyncEngine, challenge_id: UUID) -> None:
    async with async_sessionmaker(engine).begin() as session:
        await session.execute(
            update(EmailChallengeRecord)
            .where(EmailChallengeRecord.id == challenge_id)
            .values(
                created_at=func.clock_timestamp() - timedelta(minutes=1),
                resend_at=func.clock_timestamp() - timedelta(seconds=1),
            )
        )


async def test_start_is_durable_idempotent_and_does_not_grant_membership(
    identity_engine: AsyncEngine,
) -> None:
    credential = await actor(identity_engine)
    start, _ = services(identity_engine)
    command = start_command(credential)
    first, repeated = await asyncio.gather(start(command), start(command))
    assert first == repeated
    assert (await code_for(identity_engine, first.id)).value
    async with async_sessionmaker(identity_engine)() as session:
        assert (
            await session.scalars(select(func.count()).select_from(EmailDeliveryRecord))
        ).one() == 1
        assert (
            await session.scalars(select(func.count()).select_from(InstitutionalBindingRecord))
        ).one() == 0
        assert (await session.scalars(select(func.count()).select_from(SessionRecord))).one() == 1
    with pytest.raises(IdempotencyConflictError):
        await start(replace(command, email=StudentEmail("other@mail.apu.edu.my")))
    with pytest.raises(EmailRateLimitedError):
        await start(start_command(credential))


async def test_wrong_attempts_are_committed_and_same_intent_does_not_guess_twice(
    identity_engine: AsyncEngine,
) -> None:
    credential = await actor(identity_engine)
    start, verify = services(identity_engine)
    challenge = await start(start_command(credential))
    actual = await code_for(identity_engine, challenge.id)
    wrong = VerificationCode("000001" if actual.value == "000000" else "000000")
    first_command = verify_command(credential, challenge, wrong)
    first = await verify(first_command)
    assert first.outcome == VerificationOutcome.WRONG
    assert await verify(first_command) == first
    for attempt in range(2, LAST_WRONG_ATTEMPT + 1):
        result = await verify(verify_command(credential, challenge, wrong))
        assert result.attempts_remaining == LAST_WRONG_ATTEMPT - attempt
        assert result.outcome == (
            VerificationOutcome.LOCKED
            if attempt == LAST_WRONG_ATTEMPT
            else VerificationOutcome.WRONG
        )
    assert (
        await verify(verify_command(credential, challenge, actual))
    ).outcome == VerificationOutcome.LOCKED
    async with async_sessionmaker(identity_engine)() as session:
        stored = await session.get(EmailChallengeRecord, challenge.id)
        assert stored is not None
        assert stored.attempts == LAST_WRONG_ATTEMPT
        assert stored.code_digest is None


async def test_verification_replay_returns_same_nonsecret_result_and_never_new_session(
    identity_engine: AsyncEngine,
) -> None:
    credential = await actor(identity_engine)
    start, verify = services(identity_engine)
    challenge = await start(start_command(credential))
    command = verify_command(credential, challenge, await code_for(identity_engine, challenge.id))
    first, repeated = await asyncio.gather(verify(command), verify(command))
    assert first == repeated
    assert first.outcome == VerificationOutcome.VERIFIED
    assert first.verified_at is not None
    assert (
        await verify(replace(command, intent_key=IntentKey(str(uuid4()))))
    ).outcome == VerificationOutcome.UNAVAILABLE
    with pytest.raises(IdempotencyConflictError):
        await verify(
            replace(
                command,
                code=VerificationCode("000001" if command.code.value == "000000" else "000000"),
            )
        )
    reader = ReadIdentity(
        SqlIdentityUnitOfWork(async_sessionmaker(identity_engine)), Sha256SessionHasher()
    )
    assert (await reader(credential)).membership is not None
    async with async_sessionmaker(identity_engine)() as session:
        assert (await session.scalars(select(func.count()).select_from(SessionRecord))).one() == 1
        stored = await session.get(EmailChallengeRecord, challenge.id)
        assert stored is not None
        assert stored.code_digest is None
        delivery = (await session.scalars(select(EmailDeliveryRecord))).one()
        assert delivery.status == "cancelled"
        assert delivery.sealed_envelope is None
    with pytest.raises(EmailActionDeniedError):
        await start(start_command(credential))


async def test_wrong_account_or_session_cannot_verify_another_challenge(
    identity_engine: AsyncEngine,
) -> None:
    credential = await actor(identity_engine)
    other = await actor(identity_engine)
    start, verify = services(identity_engine)
    challenge = await start(start_command(credential))
    code = await code_for(identity_engine, challenge.id)
    with pytest.raises(EmailChallengeUnavailableError):
        await verify(verify_command(other, challenge, code))
    reader = ReadIdentity(
        SqlIdentityUnitOfWork(async_sessionmaker(identity_engine)), Sha256SessionHasher()
    )
    alternate_session = await actor(identity_engine, (await reader(credential)).session.account_id)
    with pytest.raises(EmailChallengeUnavailableError):
        await verify(verify_command(alternate_session, challenge, code))
    assert (
        await verify(verify_command(credential, challenge, code))
    ).outcome == VerificationOutcome.VERIFIED


async def test_resend_supersedes_code_and_erases_old_delivery(identity_engine: AsyncEngine) -> None:
    credential = await actor(identity_engine)
    start, verify = services(identity_engine)
    first = await start(start_command(credential))
    old_code = await code_for(identity_engine, first.id)
    await allow_resend(identity_engine, first.id)
    with pytest.raises(EmailChallengeUnavailableError):
        await start(replace(start_command(credential), resend_of=uuid4()))
    second = await start(replace(start_command(credential), resend_of=first.id))
    assert second.id != first.id
    assert (
        await verify(verify_command(credential, first, old_code))
    ).outcome == VerificationOutcome.UNAVAILABLE
    assert (
        await verify(verify_command(credential, second, await code_for(identity_engine, second.id)))
    ).outcome == VerificationOutcome.VERIFIED


async def test_expired_code_does_not_bind_membership(identity_engine: AsyncEngine) -> None:
    credential = await actor(identity_engine)
    start, verify = services(identity_engine)
    challenge = await start(start_command(credential))
    code = await code_for(identity_engine, challenge.id)
    async with async_sessionmaker(identity_engine).begin() as session:
        await session.execute(
            update(EmailChallengeRecord)
            .where(EmailChallengeRecord.id == challenge.id)
            .values(
                created_at=func.clock_timestamp() - timedelta(minutes=11),
                resend_at=func.clock_timestamp() - timedelta(minutes=10),
                expires_at=func.clock_timestamp() - timedelta(seconds=1),
            )
        )
    assert (
        await verify(verify_command(credential, challenge, code))
    ).outcome == VerificationOutcome.EXPIRED


async def test_competing_accounts_cannot_transfer_same_mailbox(
    identity_engine: AsyncEngine,
) -> None:
    first, second = await actor(identity_engine), await actor(identity_engine)
    start, verify = services(identity_engine)
    challenges = await asyncio.gather(start(start_command(first)), start(start_command(second)))
    codes = [await code_for(identity_engine, challenge.id) for challenge in challenges]
    results = await asyncio.gather(
        *(
            verify(verify_command(credential, challenge, code))
            for credential, challenge, code in zip((first, second), challenges, codes, strict=True)
        )
    )
    assert {result.outcome for result in results} == {
        VerificationOutcome.VERIFIED,
        VerificationOutcome.SUPPORT_REQUIRED,
    }
    reader = ReadIdentity(
        SqlIdentityUnitOfWork(async_sessionmaker(identity_engine)), Sha256SessionHasher()
    )
    status_reader = ReadEmailChallenge(
        SqlEmailUnitOfWork(async_sessionmaker(identity_engine)), Sha256SessionHasher()
    )
    for credential, challenge, result in zip((first, second), challenges, results, strict=True):
        identity = await reader(credential)
        status = await status_reader(ReadChallengeCommand(credential, challenge.id, SOURCE))
        assert status.verification_outcome == result.outcome
        assert not status.can_verify
        assert not status.can_resend
        assert identity.email_challenge_id == (
            challenge.id if result.outcome == VerificationOutcome.SUPPORT_REQUIRED else None
        )
    async with async_sessionmaker(identity_engine)() as session:
        assert (
            await session.scalars(select(func.count()).select_from(InstitutionalBindingRecord))
        ).one() == 1


@pytest.mark.parametrize("dimension", ["account", "address", "source"])
async def test_delivery_quotas_are_atomic_across_competing_starts(
    identity_engine: AsyncEngine, dimension: str
) -> None:
    credential = await actor(identity_engine)
    policy = EmailPolicy(
        deliveries_per_account=1 if dimension == "account" else 5,
        deliveries_per_address=1 if dimension == "address" else 5,
        starts_per_source=1 if dimension == "source" else 30,
    )
    start, _ = services(identity_engine, policy)
    other = credential if dimension == "account" else await actor(identity_engine)
    address = EMAIL if dimension == "address" else StudentEmail("other@mail.apu.edu.my")

    async def submit(command: StartChallengeCommand) -> bool:
        try:
            await start(command)
        except EmailRateLimitedError:
            return False
        return True

    assert sorted(
        await asyncio.gather(
            submit(start_command(credential)),
            submit(start_command(other, address)),
        )
    ) == [False, True]
    async with async_sessionmaker(identity_engine)() as session:
        assert (
            await session.scalars(select(func.count()).select_from(EmailDeliveryRecord))
        ).one() == 1


@pytest.mark.parametrize("field", ["banned_at", "deleted_at"])
async def test_lifecycle_denies_new_delivery_and_verification(
    identity_engine: AsyncEngine, field: str
) -> None:
    credential = await actor(identity_engine)
    start, verify = services(identity_engine)
    challenge = await start(start_command(credential))
    code = await code_for(identity_engine, challenge.id)
    async with async_sessionmaker(identity_engine).begin() as session:
        await session.execute(update(AccountRecord).values({field: func.clock_timestamp()}))
    error = EmailActionDeniedError if field == "banned_at" else UnauthenticatedError
    with pytest.raises(error):
        await start(start_command(credential))
    with pytest.raises(error):
        await verify(verify_command(credential, challenge, code))


@pytest.mark.parametrize("dimension", ["account", "address", "source"])
async def test_status_reports_quota_deadline_without_consuming_budget(
    identity_engine: AsyncEngine, dimension: str
) -> None:
    credential = await actor(identity_engine)
    policy = EmailPolicy(
        deliveries_per_account=1 if dimension == "account" else 5,
        deliveries_per_address=1 if dimension == "address" else 5,
        starts_per_source=1 if dimension == "source" else 30,
    )
    start, _ = services(identity_engine, policy)
    challenge = await start(start_command(credential))
    await allow_resend(identity_engine, challenge.id)
    async with async_sessionmaker(identity_engine)() as session:
        stored = await session.get(EmailChallengeRecord, challenge.id)
        assert stored is not None
        expected_retry = stored.created_at + timedelta(hours=1)
    reader = ReadEmailChallenge(
        SqlEmailUnitOfWork(async_sessionmaker(identity_engine)), Sha256SessionHasher(), policy
    )
    command = ReadChallengeCommand(credential, challenge.id, SOURCE)
    status = await reader(command)
    assert status == await reader(command)
    assert status.resend_at == expected_retry
    assert status.can_verify
    assert not status.can_resend
    with pytest.raises(EmailRateLimitedError) as limited:
        await start(start_command(credential))
    assert limited.value.retry_at == expected_retry


async def test_logout_and_verification_race_never_restores_session(
    identity_engine: AsyncEngine,
) -> None:
    credential = await actor(identity_engine)
    start, verify = services(identity_engine)
    challenge = await start(start_command(credential))
    command = verify_command(credential, challenge, await code_for(identity_engine, challenge.id))
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    logout = Logout(SqlIdentityUnitOfWork(sessions), Sha256SessionHasher())

    async def verification() -> bool:
        try:
            result = await verify(command)
        except UnauthenticatedError:
            return False
        return result.outcome == VerificationOutcome.VERIFIED

    verified, _ = await asyncio.gather(verification(), logout(credential))
    with pytest.raises(UnauthenticatedError):
        await ReadIdentity(SqlIdentityUnitOfWork(sessions), Sha256SessionHasher())(credential)
    async with sessions() as session:
        assert (
            await session.scalars(select(func.count()).select_from(InstitutionalBindingRecord))
        ).one() == int(verified)
