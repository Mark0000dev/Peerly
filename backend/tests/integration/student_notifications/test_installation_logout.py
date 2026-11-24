"""Real asyncpg transaction regressions; requires reserved0064, never create_all."""

import asyncio
import base64
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import Logout, SessionCredential
from studymate.application.student_notifications.subscriptions import (
    InstallationLogoutTransaction,
    LogoutInstallation,
    RegisterDeviceCommand,
    RegisterOwnDelivery,
    RetirementDisposition,
    SubscriptionVersionError,
)
from studymate.domain.student_notifications.capabilities import (
    Capabilities,
    Platform,
    Registration,
)
from studymate.infrastructure.persistence.identity_models import SessionRecord
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityUnitOfWork
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from studymate.infrastructure.student_notifications.capabilities import (
    DeviceAttemptRecord,
)
from studymate.infrastructure.student_notifications.queue import (
    SqlStudentNotifications,
    clock,
    transaction,
)
from studymate.infrastructure.student_notifications.subscriptions import (
    SqlInstallationLogoutTransaction,
    SqlInstallationLogoutUnitOfWork,
    SqlSubscriptionUnitOfWork,
    SubscriptionRecord,
)
from tests.integration.student_actor import Actor, actor
from tests.integration.test_message_commands import chat

pytestmark = pytest.mark.integration
HASHER = Sha256SessionHasher()
SECOND_VERSION = 2


def registration(engine: AsyncEngine) -> RegisterOwnDelivery:
    return RegisterOwnDelivery(
        SqlSubscriptionUnitOfWork(
            async_sessionmaker(engine, expire_on_commit=False),
            Fernet(base64.urlsafe_b64encode(bytes(range(32)))),
            (),
        ),
        HASHER,
        HmacIntentFingerprinter(bytes(range(32))),
        Capabilities(android=True),
    )


def logout(engine: AsyncEngine) -> LogoutInstallation:
    return LogoutInstallation(
        SqlInstallationLogoutUnitOfWork(async_sessionmaker(engine, expire_on_commit=False)),
        HASHER,
    )


def command(student: Actor, installation: UUID, version: int = 0) -> RegisterDeviceCommand:
    return RegisterDeviceCommand(
        student.credential,
        Registration(installation, Platform.ANDROID, True, "Asia/Kuala_Lumpur", "synthetic-token"),
        version,
        IntentKey(str(uuid4())),
    )


async def session_row(session: AsyncSession, credential: SessionCredential) -> SessionRecord:
    return (
        await session.scalars(
            select(SessionRecord).where(
                SessionRecord.secret_digest == await HASHER.digest(credential)
            )
        )
    ).one()


async def newer_session(engine: AsyncEngine, student: Actor) -> Actor:
    value = Actor(student.id, SessionCredential(uuid4().hex + uuid4().hex[:11]))
    async with async_sessionmaker(engine).begin() as session:
        now = await clock(session)
        session.add(
            SessionRecord(
                id=uuid4(),
                account_id=student.id,
                secret_digest=await HASHER.digest(value.credential),
                issued_at=now,
                expires_at=now + timedelta(days=1),
            )
        )
    return value


async def test_same_session_registration_material_is_retired_with_session_revoke(
    identity_engine: AsyncEngine,
) -> None:
    student, installation = (await actor(identity_engine), uuid4())
    await registration(identity_engine)(command(student, installation))
    assert (
        await logout(identity_engine)(student.credential, installation)
        == RetirementDisposition.RETIRED
    )
    async with async_sessionmaker(identity_engine)() as session:
        row = await session.get(SubscriptionRecord, (student.id, installation))
        assert row is not None
        assert not row.enabled
        assert row.version == SECOND_VERSION
        assert row.sealed_material is row.endpoint_digest is row.material_digest is None
        stored = await session_row(session, student.credential)
        assert stored.id == row.enrolled_session_id
        assert stored.revoked_at is not None


async def test_newer_session_enrollment_survives_old_credential_logout(
    identity_engine: AsyncEngine,
) -> None:
    student, installation = (await actor(identity_engine), uuid4())
    await registration(identity_engine)(command(student, installation))
    newer = await newer_session(identity_engine, student)
    await registration(identity_engine)(command(newer, installation, 1))
    assert (
        await logout(identity_engine)(student.credential, installation)
        == RetirementDisposition.UNCONFIRMED
    )
    async with async_sessionmaker(identity_engine)() as session:
        row = await session.get(SubscriptionRecord, (student.id, installation))
        assert row is not None
        assert row.enabled
        assert row.version == SECOND_VERSION
        assert row.enrolled_session_id == (await session_row(session, newer.credential)).id
        assert (await session_row(session, newer.credential)).revoked_at is None
        assert (await session_row(session, student.credential)).revoked_at is not None


async def test_foreign_installation_is_not_retired_and_no_input_logout_is_unchanged(
    identity_engine: AsyncEngine,
) -> None:
    student, foreign = (await actor(identity_engine), await actor(identity_engine))
    installation = uuid4()
    await registration(identity_engine)(command(foreign, installation))
    assert (
        await logout(identity_engine)(student.credential, installation)
        == RetirementDisposition.UNCONFIRMED
    )
    await Logout(SqlIdentityUnitOfWork(async_sessionmaker(identity_engine)), HASHER)(
        foreign.credential
    )
    async with async_sessionmaker(identity_engine)() as session:
        row = await session.get(SubscriptionRecord, (foreign.id, installation))
        assert row is not None
        assert row.enabled
        assert (await session_row(session, student.credential)).revoked_at is not None
        assert (await session_row(session, foreign.credential)).revoked_at is not None


@dataclass(frozen=True, slots=True)
class FailedRevoke(SqlInstallationLogoutTransaction):
    async def revoke_session(self, session_id: UUID, at: datetime) -> None:
        await SqlInstallationLogoutTransaction.revoke_session(self, session_id, at)
        raise RuntimeError("Synthetic post-revoke failure")


@dataclass(frozen=True, slots=True)
class FailedUnit:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[InstallationLogoutTransaction]:
        async with transaction(self.sessions) as session:
            yield FailedRevoke(session)


async def test_actual_post_revoke_failure_rolls_back_material_and_session(
    identity_engine: AsyncEngine,
) -> None:
    student, installation = (await actor(identity_engine), uuid4())
    await registration(identity_engine)(command(student, installation))
    unit = FailedUnit(async_sessionmaker(identity_engine, expire_on_commit=False))
    with pytest.raises(RuntimeError, match="Synthetic post-revoke"):
        await LogoutInstallation(unit, HASHER)(student.credential, installation)
    async with async_sessionmaker(identity_engine)() as session:
        row = await session.get(SubscriptionRecord, (student.id, installation))
        assert row is not None
        assert row.enabled
        assert row.version == 1
        assert row.sealed_material is not None
        assert (await session_row(session, student.credential)).revoked_at is None


async def test_concurrent_old_logout_and_new_enrollment_do_not_erase_newer_owner(
    identity_engine: AsyncEngine,
) -> None:
    student, installation = (await actor(identity_engine), uuid4())
    await registration(identity_engine)(command(student, installation))
    newer = await newer_session(identity_engine, student)

    async def enroll() -> bool:
        try:
            await registration(identity_engine)(command(newer, installation, 1))
        except SubscriptionVersionError:
            return False
        return True

    retired, enrolled = await asyncio.gather(
        logout(identity_engine)(student.credential, installation), enroll()
    )
    async with async_sessionmaker(identity_engine)() as session:
        row = await session.get(SubscriptionRecord, (student.id, installation))
        assert row is not None
        assert row.version == SECOND_VERSION
        assert (await session_row(session, student.credential)).revoked_at is not None
        if enrolled:
            assert retired == RetirementDisposition.UNCONFIRMED
            assert row.enabled
            assert row.enrolled_session_id == (await session_row(session, newer.credential)).id
        else:
            assert retired == RetirementDisposition.RETIRED
            assert not row.enabled


async def test_dispatch_attempts_are_fenced_only_for_retired_installation(
    identity_engine: AsyncEngine,
) -> None:
    thread = await chat(identity_engine)
    first, other = (uuid4(), uuid4())
    register = registration(identity_engine)
    await register(command(thread.recipient, first))
    other_session = await newer_session(identity_engine, thread.recipient)
    value = command(other_session, other)
    from dataclasses import replace

    await register(
        replace(value, registration=replace(value.registration, endpoint="another-token"))
    )
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    notifications = SqlStudentNotifications(sessions)
    await notifications.activate()
    await thread.send()(thread.command())
    assert await notifications.materialize() == 1
    claim = await notifications.claim()
    assert claim is not None
    assert await notifications.authorize(claim) is not None
    async with sessions.begin() as session:
        now = await clock(session)
        session.add_all(
            [
                DeviceAttemptRecord(
                    delivery_id=claim.delivery.id,
                    account_id=thread.recipient.id,
                    installation_id=first,
                    state="sending",
                    generation=1,
                    lease_until=now + timedelta(seconds=30),
                ),
                DeviceAttemptRecord(
                    delivery_id=claim.delivery.id,
                    account_id=thread.recipient.id,
                    installation_id=other,
                    state="retryable",
                    generation=1,
                    lease_until=now + timedelta(seconds=30),
                ),
            ]
        )
    assert (
        await logout(identity_engine)(thread.recipient.credential, first)
        == RetirementDisposition.RETIRED
    )
    async with sessions() as session:
        attempts = {
            row.installation_id: row.state
            for row in (await session.scalars(select(DeviceAttemptRecord))).all()
        }
        assert attempts == {first: "unknown", other: "retryable"}
        other_row = await session.get(SubscriptionRecord, (thread.recipient.id, other))
        assert other_row is not None
        assert other_row.enabled


async def test_enrollment_session_composite_foreign_key_rejects_other_account(
    identity_engine: AsyncEngine,
) -> None:
    student, foreign = (await actor(identity_engine), await actor(identity_engine))
    installation = uuid4()
    await registration(identity_engine)(command(student, installation))

    async def change_enrollment() -> None:
        async with async_sessionmaker(identity_engine).begin() as session:
            row = await session.get(SubscriptionRecord, (student.id, installation))
            assert row is not None
            row.enrolled_session_id = (await session_row(session, foreign.credential)).id
            await session.flush()

    with pytest.raises(IntegrityError) as caught:
        await change_enrollment()
    assert getattr(caught.value.orig, "sqlstate", None) == "23503"
