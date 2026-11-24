"""Real migrated PostgreSQL session-enrollment lifecycle; no provider network."""

import asyncio
import base64
from dataclasses import replace
from uuid import uuid4

import httpx2 as httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.student_notifications.subscriptions import (
    RetirementDisposition,
    SubscriptionVersionError,
)
from studymate.domain.student_notifications.capabilities import Platform
from studymate.domain.student_notifications.delivery import Delivery, Outcome
from studymate.infrastructure.student_notifications.capabilities import (
    SubscribedPushDelivery,
)
from studymate.infrastructure.student_notifications.providers import PushProviders
from studymate.infrastructure.student_notifications.queue import SqlStudentNotifications
from studymate.infrastructure.student_notifications.subscriptions import (
    SubscriptionRecord,
)
from tests.integration.student_actor import actor
from tests.integration.student_notifications.test_installation_logout import (
    command,
    logout,
    newer_session,
    registration,
    session_row,
)
from tests.integration.test_message_commands import chat

HISTORICAL_COUNT = 9
ACTIVE_LIMIT = 8
RETIRED_VERSION = 2

pytestmark = pytest.mark.integration


class NoDispatch(PushProviders):
    async def send(
        self,
        delivery: Delivery,
        platform: Platform,
        endpoint: str,
        public: str | None,
        auth: str | None,
    ) -> Outcome:
        assert delivery.id is not None
        assert platform in tuple(Platform)
        assert isinstance(endpoint, str)
        assert public is None or isinstance(public, str)
        assert auth is None or isinstance(auth, str)
        raise AssertionError("Revoked enrollment reached provider boundary")


async def test_missing_id_retires_all_current_session_material_and_no_old_fanout(
    identity_engine: AsyncEngine,
) -> None:
    thread = await chat(identity_engine)
    installation = uuid4()
    await registration(identity_engine)(command(thread.recipient, installation))
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    queue = SqlStudentNotifications(sessions)
    await queue.activate()
    await thread.send()(thread.command())
    assert await queue.materialize() == 1
    claim = await queue.claim()
    assert claim is not None
    delivery = await queue.authorize(claim)
    assert delivery is not None
    assert (
        await logout(identity_engine)(thread.recipient.credential)
        == RetirementDisposition.UNCONFIRMED
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(500))
    ) as client:
        transport = SubscribedPushDelivery(
            sessions,
            Fernet(base64.urlsafe_b64encode(bytes(range(32)))),
            NoDispatch(client),
        )
        assert await transport.send(delivery) == Outcome.REJECTED
    async with sessions() as session:
        row = await session.get(SubscriptionRecord, (thread.recipient.id, installation))
        assert row is not None
        assert not row.enabled
        assert row.sealed_material is row.endpoint_digest is row.material_digest is None
        assert (await session_row(session, thread.recipient.credential)).revoked_at is not None


async def test_missing_id_preserves_newer_and_foreign_session_enrollments(
    identity_engine: AsyncEngine,
) -> None:
    student, foreign = (await actor(identity_engine), await actor(identity_engine))
    newer = await newer_session(identity_engine, student)
    ids = [uuid4(), uuid4(), uuid4()]
    for owner, installation, token in [
        (student, ids[0], "old"),
        (newer, ids[1], "new"),
        (foreign, ids[2], "foreign"),
    ]:
        value = command(owner, installation)
        await registration(identity_engine)(
            replace(value, registration=replace(value.registration, endpoint=token))
        )
    await logout(identity_engine)(student.credential)
    async with async_sessionmaker(identity_engine)() as session:
        old = await session.get(SubscriptionRecord, (student.id, ids[0]))
        new = await session.get(SubscriptionRecord, (student.id, ids[1]))
        other = await session.get(SubscriptionRecord, (foreign.id, ids[2]))
        assert old is not None
        assert not old.enabled
        assert new is not None
        assert new.enabled
        assert other is not None
        assert other.enabled
        assert (await session_row(session, newer.credential)).revoked_at is None
        assert (await session_row(session, foreign.credential)).revoked_at is None


async def test_same_endpoint_new_id_after_retirement_preserves_tombstone(
    identity_engine: AsyncEngine,
) -> None:
    student = await actor(identity_engine)
    old, new = (uuid4(), uuid4())
    await registration(identity_engine)(command(student, old))
    await logout(identity_engine)(student.credential)
    newer = await newer_session(identity_engine, student)
    await registration(identity_engine)(command(newer, new))
    async with async_sessionmaker(identity_engine)() as session:
        historical = await session.get(SubscriptionRecord, (student.id, old))
        current = await session.get(SubscriptionRecord, (student.id, new))
        assert historical is not None
        assert not historical.enabled
        assert historical.version == RETIRED_VERSION
        assert historical.endpoint_digest is None
        assert current is not None
        assert current.enabled
        assert current.version == 1


async def test_eight_active_limit_ignores_more_than_eight_retired_rows(
    identity_engine: AsyncEngine,
) -> None:
    student = await actor(identity_engine)
    register = registration(identity_engine)
    for index in range(9):
        value = command(student, uuid4())
        value = replace(
            value, registration=replace(value.registration, endpoint=f"retired-{index}")
        )
        await register(value)
        await register(
            replace(
                value,
                registration=replace(value.registration, enabled=False, endpoint=None),
                expected_version=1,
                intent_key=type(value.intent_key)(str(uuid4())),
            )
        )
    for index in range(8):
        value = command(student, uuid4())
        await register(
            replace(
                value,
                registration=replace(value.registration, endpoint=f"active-{index}"),
            )
        )
    value = command(student, uuid4())
    with pytest.raises(SubscriptionVersionError):
        await register(
            replace(value, registration=replace(value.registration, endpoint="ninth-active"))
        )
    async with async_sessionmaker(identity_engine)() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(SubscriptionRecord)
                .where(SubscriptionRecord.account_id == student.id)
            )
            == HISTORICAL_COUNT + ACTIVE_LIMIT
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(SubscriptionRecord)
                .where(
                    SubscriptionRecord.account_id == student.id,
                    SubscriptionRecord.enabled.is_(True),
                )
            )
            == ACTIVE_LIMIT
        )


async def test_missing_id_logout_races_newer_enrollment_without_erasing_new_owner(
    identity_engine: AsyncEngine,
) -> None:
    student = await actor(identity_engine)
    installation = uuid4()
    await registration(identity_engine)(command(student, installation))
    newer = await newer_session(identity_engine, student)

    async def enroll() -> bool:
        try:
            await registration(identity_engine)(command(newer, installation, 1))
        except SubscriptionVersionError:
            return False
        return True

    _, enrolled = await asyncio.gather(logout(identity_engine)(student.credential), enroll())
    async with async_sessionmaker(identity_engine)() as session:
        row = await session.get(SubscriptionRecord, (student.id, installation))
        assert row is not None
        assert (await session_row(session, student.credential)).revoked_at is not None
        assert row.enabled == enrolled
        if enrolled:
            assert row.enrolled_session_id == (await session_row(session, newer.credential)).id


async def test_explicit_revoked_session_defensively_rejected_even_with_enabled_material(
    identity_engine: AsyncEngine,
) -> None:
    from studymate.application.identity.sessions import Logout
    from studymate.infrastructure.persistence.identity_sessions import (
        SqlIdentityUnitOfWork,
    )
    from tests.integration.student_notifications.test_installation_logout import HASHER

    thread = await chat(identity_engine)
    installation = uuid4()
    await registration(identity_engine)(command(thread.recipient, installation))
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    queue = SqlStudentNotifications(sessions)
    await queue.activate()
    await thread.send()(thread.command())
    assert await queue.materialize() == 1
    claim = await queue.claim()
    assert claim is not None
    delivery = await queue.authorize(claim)
    assert delivery is not None
    await Logout(SqlIdentityUnitOfWork(sessions), HASHER)(thread.recipient.credential)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(500))
    ) as client:
        transport = SubscribedPushDelivery(
            sessions,
            Fernet(base64.urlsafe_b64encode(bytes(range(32)))),
            NoDispatch(client),
        )
        assert await transport.send(delivery) == Outcome.REJECTED


async def test_logout_fences_inflight_provider_completion_as_unknown(
    identity_engine: AsyncEngine,
) -> None:
    from dataclasses import dataclass

    from studymate.infrastructure.student_notifications.capabilities import (
        DeviceAttemptRecord,
    )

    @dataclass(frozen=True, slots=True)
    class InFlight(PushProviders):
        entered: asyncio.Event | None = None
        release: asyncio.Event | None = None

        async def send(
            self,
            delivery: Delivery,
            platform: Platform,
            endpoint: str,
            public: str | None,
            auth: str | None,
        ) -> Outcome:
            assert delivery.id is not None
            assert platform == Platform.ANDROID
            assert endpoint == "synthetic-token"
            assert public is None
            assert auth is None
            assert self.entered is not None
            assert self.release is not None
            self.entered.set()
            await self.release.wait()
            return Outcome.ACCEPTED

    thread = await chat(identity_engine)
    installation = uuid4()
    await registration(identity_engine)(command(thread.recipient, installation))
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    queue = SqlStudentNotifications(sessions)
    await queue.activate()
    await thread.send()(thread.command())
    assert await queue.materialize() == 1
    claim = await queue.claim()
    assert claim is not None
    delivery = await queue.authorize(claim)
    assert delivery is not None
    entered, release = (asyncio.Event(), asyncio.Event())
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(500))
    ) as client:
        provider = InFlight(client, entered=entered, release=release)
        transport = SubscribedPushDelivery(
            sessions, Fernet(base64.urlsafe_b64encode(bytes(range(32)))), provider
        )
        async with asyncio.TaskGroup() as tasks:
            sending = tasks.create_task(transport.send(delivery))
            try:
                async with asyncio.timeout(2):
                    await entered.wait()
                await logout(identity_engine)(thread.recipient.credential)
            finally:
                release.set()
        assert sending.result() == Outcome.UNKNOWN
        assert await transport.send(delivery) == Outcome.REJECTED
    async with sessions() as session:
        attempt = await session.get(
            DeviceAttemptRecord, (delivery.id, thread.recipient.id, installation)
        )
        assert attempt is not None
        assert attempt.state == "unknown"
