"""Real migrated PostgreSQL registry and same-transaction metadata guards."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from deployment.backend.external_delivery_activation import (
    ActivationRejectedError,
    SupportTarget,
    Targets,
    UmamiTarget,
    build_plan,
    read_snapshot,
    register_plan,
    registrations,
)
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.domain.external_delivery.delivery import DestinationRef
from studymate.domain.external_delivery.sources import Sink
from studymate.infrastructure.external_delivery.destinations import (
    DestinationRegistration,
    register_destinations,
    register_transaction_destinations,
)
from studymate.infrastructure.external_delivery.models import (
    DeliveryDestinationRecord,
    DeliveryScheduleRecord,
)
from tests.integration.conftest import (
    engine as engine,
)
from tests.integration.conftest import (
    identity_engine as identity_engine,
)

pytestmark = pytest.mark.integration


def targets() -> Targets:
    return Targets(
        schema_version=1,
        database="peerly_staging",
        database_schema="public",
        migration_revision="0060_report_triage",
        backend_image="ghcr.io/mark0000dev/peerly-backend@sha256:" + "a" * 64,
        support_notice_not_before=datetime.now(UTC) - timedelta(minutes=1),
        umami=UmamiTarget(
            revision=1, origin="https://analytics.example.test", website_id=UUID(int=1)
        ),
        telegram_support=SupportTarget(
            revision=1,
            chat_id=-100123456,
            operator_origin="https://peerly-staging.example.test",
            topic_id=None,
        ),
    )


async def test_guarded_registration_replay_keeps_actual_fingerprints_and_times(
    identity_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    configured = targets()
    async with sessions.begin() as session:
        plan = build_plan(configured, await read_snapshot(session, configured))
    async with sessions.begin() as session:
        first = await register_plan(session, plan)
    async with sessions.begin() as session:
        replay = await register_plan(session, plan)
    assert first.registered == replay.registered
    assert len(first.registered) == len(registrations(configured))


async def test_existing_writer_rolls_back_first_insert_on_second_target_mismatch(
    identity_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    # Sorted support is inserted first; the existing Umami conflict must roll it back.
    await register_destinations(
        sessions, (DestinationRegistration(DestinationRef(Sink.UMAMI, 1), b"x" * 32),)
    )
    with pytest.raises(ValueError, match="cannot change"):
        async with sessions.begin() as session:
            await register_transaction_destinations(session, registrations(targets()))
    async with sessions() as session:
        rows = tuple((await session.scalars(select(DeliveryDestinationRecord))).all())
        assert len(rows) == 1
        assert rows[0].sink == "umami"
        assert rows[0].fingerprint == b"x" * 32


async def test_duplicate_sink_rejects_without_either_row(identity_engine: AsyncEngine) -> None:
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    item = registrations(targets())[0]
    with pytest.raises(ValueError, match="one current target"):
        await register_destinations(sessions, (item, item))
    async with sessions() as session:
        assert tuple(await session.scalars(select(DeliveryDestinationRecord))) == ()


async def test_expired_approved_snapshot_rejects_before_registry_write(
    identity_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    configured = targets()
    async with sessions.begin() as session:
        snapshot = await read_snapshot(session, configured)
    old = snapshot.model_copy(update={"captured_at": snapshot.captured_at - timedelta(minutes=6)})
    # Keep the cutoff valid so the finite rejection specifically tests freshness.
    configured = configured.model_copy(
        update={"support_notice_not_before": old.captured_at - timedelta(minutes=1)}
    )
    with pytest.raises(ActivationRejectedError, match="stale_or_future"):
        async with sessions.begin() as session:
            await register_plan(session, build_plan(configured, old))
    async with sessions() as session:
        assert tuple(await session.scalars(select(DeliveryDestinationRecord))) == ()


async def test_current_guard_failure_same_transaction_keeps_both_targets_absent(
    identity_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    configured = targets()
    async with sessions.begin() as session:
        plan = build_plan(configured, await read_snapshot(session, configured))
        await session.execute(
            update(DeliveryScheduleRecord)
            .where(DeliveryScheduleRecord.sink == "umami")
            .values(blocked_reason="credentials_unavailable")
        )
    with pytest.raises(ActivationRejectedError, match="blocked_sink"):
        async with sessions.begin() as session:
            await register_plan(session, plan)
    async with sessions() as session:
        assert tuple(await session.scalars(select(DeliveryDestinationRecord))) == ()


async def test_disabled_actual_capture_trigger_blocks_registration(
    identity_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    configured = targets()
    async with sessions.begin() as session:
        enabled = await read_snapshot(session, configured)
        assert enabled.capture_triggers_verified
        plan = build_plan(configured, enabled)
        await session.execute(
            text("ALTER TABLE product_events DISABLE TRIGGER peerly_capture_product_events")
        )
    with pytest.raises(ActivationRejectedError, match="capture_trigger_mismatch"):
        async with sessions.begin() as session:
            await register_plan(session, plan)
    async with sessions() as session:
        assert tuple(await session.scalars(select(DeliveryDestinationRecord))) == ()
