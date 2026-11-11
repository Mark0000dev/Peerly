"""Owned foreground source facts; read-only requests never warm exposure freshness."""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.application.idempotency import IntentKey
from studymate.domain.discovery_freshness import (
    DiscoveryExposure,
    DiscoveryFreshnessPolicy,
    ExposureConfirmation,
)
from studymate.infrastructure.persistence.discovery_freshness_models import (
    DiscoveryExposureRecord,
    DiscoveryFreshnessPolicyRecord,
)


async def read_freshness_policy(session: AsyncSession, at: datetime) -> DiscoveryFreshnessPolicy:
    seconds = (
        await session.scalars(
            select(DiscoveryFreshnessPolicyRecord.inactivity_seconds)
            .where(DiscoveryFreshnessPolicyRecord.published_at <= at)
            .order_by(DiscoveryFreshnessPolicyRecord.version.desc())
            .limit(1)
        )
    ).one_or_none()
    if seconds is None:
        raise RuntimeError("Published discovery freshness policy is unavailable")
    return DiscoveryFreshnessPolicy(timedelta(seconds=seconds))


def _exposure(record: DiscoveryExposureRecord) -> DiscoveryExposure:
    return DiscoveryExposure(
        record.account_id,
        record.last_activity_at,
        record.confirmed_at,
        record.paused_at,
        timedelta(seconds=record.inactivity_seconds),
    )


def _assign(record: DiscoveryExposureRecord, value: DiscoveryExposure) -> None:
    record.inactivity_seconds = int(value.inactivity.total_seconds())
    record.last_activity_at = value.last_activity_at
    record.confirmed_at = value.confirmed_at
    record.paused_at = value.paused_at


async def read_discovery_exposure(
    session: AsyncSession, account_id: UUID
) -> DiscoveryExposure | None:
    record = await session.get(DiscoveryExposureRecord, account_id)
    return _exposure(record) if record is not None else None


async def initialize_discovery_exposure(
    session: AsyncSession, account_id: UUID, at: datetime
) -> None:
    policy = await read_freshness_policy(session, at)
    session.add(
        DiscoveryExposureRecord(
            account_id=account_id,
            inactivity_seconds=int(policy.inactivity.total_seconds()),
            last_activity_at=at,
            confirmed_at=at,
            paused_at=None,
            confirmation_key=None,
        )
    )
    await session.flush()


async def record_foreground_activity(session: AsyncSession, account_id: UUID, at: datetime) -> None:
    record = await session.get(DiscoveryExposureRecord, account_id)
    # Draft/unregistered accounts have no published exposure to pause.
    if record is None:
        return
    policy = await read_freshness_policy(session, at)
    _assign(record, _exposure(record).record_foreground_activity(at, policy))
    await session.flush()


async def confirm_discovery_exposure(
    session: AsyncSession,
    account_id: UUID,
    key: IntentKey,
    at: datetime,
) -> ExposureConfirmation | None:
    record = await session.get(DiscoveryExposureRecord, account_id)
    if record is None:
        raise RuntimeError("Completed profile exposure source is unavailable")
    policy = await read_freshness_policy(session, at)
    value, confirmation = _exposure(record).confirm_exposure(at, policy)
    _assign(record, value)
    if confirmation is not None:
        record.confirmation_key = key.value
    await session.flush()
    return confirmation
