"""Real0063/0064 aggregate reads, own pool1, no provider or sealed material projection."""

from datetime import timedelta
from uuid import uuid4

import pytest
from opentelemetry.metrics import CallbackOptions
from opentelemetry.sdk.metrics import MeterProvider
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from studymate.domain.student_notifications.capabilities import Platform
from studymate.domain.student_notifications.delivery import Outcome, State
from studymate.infrastructure.observability.student_notifications import (
    DEVICE_DIMENSIONS,
    DeviceAttemptState,
    SqlStudentNotificationReader,
    StudentNotificationSignals,
)
from studymate.infrastructure.persistence.identity_models import SessionRecord
from studymate.infrastructure.student_notifications.capabilities import DeviceAttemptRecord
from studymate.infrastructure.student_notifications.models import DeliveryRecord
from studymate.infrastructure.student_notifications.queue import SqlStudentNotifications, clock
from studymate.infrastructure.student_notifications.subscriptions import SubscriptionRecord
from tests.integration.requests.fixture import prepared, sent

pytestmark = pytest.mark.integration
DUE_AGE = 60


async def pool_one(engine: AsyncEngine) -> AsyncEngine:
    async with engine.connect() as connection:
        schema = await connection.scalar(text("SELECT current_schema()"))
    if not isinstance(schema, str) or not schema.startswith("test_"):
        raise ValueError("Migrated disposable schema required")
    return create_async_engine(
        engine.url,
        pool_size=1,
        max_overflow=0,
        pool_timeout=2,
        connect_args={
            "server_settings": {
                "search_path": schema,
                "statement_timeout": "1500",
                "lock_timeout": "1000",
            }
        },
    )


async def test_empty_snapshot_and_transaction_settings_return_to_pool(
    identity_engine: AsyncEngine,
) -> None:
    engine = await pool_one(identity_engine)
    try:
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        value = await SqlStudentNotificationReader(sessions).snapshot()
        assert value.queue == (0,) * len(State)
        assert value.devices == (0,) * len(DEVICE_DIMENSIONS)
        assert value.device_attempts == (0,) * len(DeviceAttemptState)
        assert value.oldest_due_seconds == 0
        async with engine.connect() as connection:
            assert await connection.scalar(text("SHOW transaction_read_only")) == "off"
            assert await connection.scalar(text("SHOW statement_timeout")) == "1500ms"
            assert await connection.scalar(text("SHOW lock_timeout")) == "1s"
    finally:
        await engine.dispose()


async def test_real_queue_due_age_devices_and_ambiguous_attempt_states(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    queue = SqlStudentNotifications(sessions)
    await queue.activate()
    await sent(api, sender, recipient)
    assert await queue.materialize() == 1
    async with sessions.begin() as session:
        now = await clock(session)
        await session.execute(
            update(DeliveryRecord).values(
                created_at=now - timedelta(seconds=120), due_at=now - timedelta(seconds=DUE_AGE)
            )
        )
        session_id = await session.scalar(
            select(SessionRecord.id).where(SessionRecord.account_id == recipient.id).limit(1)
        )
        assert session_id is not None
        delivery_id = await session.scalar(select(DeliveryRecord.id))
        assert delivery_id is not None
        installation = uuid4()
        # Real migrated constraint-backed rows, synthetic private material never selected by reader.
        session.add(
            SubscriptionRecord(
                account_id=recipient.id,
                installation_id=installation,
                enrolled_session_id=session_id,
                platform="web",
                timezone=None,
                version=1,
                enabled=True,
                endpoint_digest=b"d" * 32,
                sealed_material=b"PRIVATE_SEALED_SENTINEL",
                material_digest=b"m" * 32,
                updated_at=now,
            )
        )
        await session.flush()
        session.add(
            DeviceAttemptRecord(
                delivery_id=delivery_id,
                account_id=recipient.id,
                installation_id=installation,
                state="unknown",
                lease_until=now + timedelta(seconds=30),
                generation=1,
            )
        )
    engine = await pool_one(identity_engine)
    try:
        reader = SqlStudentNotificationReader(async_sessionmaker(engine, expire_on_commit=False))
        before = await reader.snapshot()
        assert before.queue[tuple(State).index(State.PENDING)] == 1
        assert before.oldest_due_seconds >= DUE_AGE
        assert before.devices[DEVICE_DIMENSIONS.index((Platform.WEB, True))] == 1
        assert (
            before.device_attempts[tuple(DeviceAttemptState).index(DeviceAttemptState.UNKNOWN)] == 1
        )
        claim = await queue.claim()
        assert claim is not None
        assert await queue.authorize(claim) is not None
        assert await queue.finish(claim, Outcome.UNKNOWN)
        after = await reader.snapshot()
        assert after.queue[tuple(State).index(State.UNKNOWN)] == 1
        assert after.queue[tuple(State).index(State.PENDING)] == 0
        assert after.oldest_due_seconds == 0
        assert "PRIVATE_SEALED_SENTINEL" not in repr(after)
    finally:
        await engine.dispose()


async def test_actual_lock_timeout_invalidates_snapshot_then_recovers(
    identity_engine: AsyncEngine,
) -> None:
    engine = await pool_one(identity_engine)
    provider = MeterProvider(shutdown_on_exit=False)
    signals = StudentNotificationSignals(provider.get_meter("test"), expected=True)
    reader = SqlStudentNotificationReader(async_sessionmaker(engine, expire_on_commit=False))
    try:
        assert await signals.sample(reader)
        async with identity_engine.begin() as blocker:
            await blocker.execute(
                text("LOCK TABLE student_notification_deliveries IN ACCESS EXCLUSIVE MODE")
            )
            assert not await signals.sample(reader)
            assert signals.depth(CallbackOptions()) == ()
            assert signals.fresh(CallbackOptions())[0].value == 0
        assert await signals.sample(reader)
        assert signals.fresh(CallbackOptions())[0].value == 1
    finally:
        signals.close()
        provider.shutdown()
        await engine.dispose()
