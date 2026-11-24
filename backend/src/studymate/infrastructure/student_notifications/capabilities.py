"""Configured-provider capability and durable per-device ambiguity fencing."""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID

from cryptography.fernet import Fernet
from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from studymate.domain.student_notifications.capabilities import Platform
from studymate.domain.student_notifications.delivery import Delivery, Outcome
from studymate.infrastructure.persistence.base import Base
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    SessionRecord,
)
from studymate.infrastructure.student_notifications.providers import PushProviders
from studymate.infrastructure.student_notifications.queue import clock, transaction
from studymate.infrastructure.student_notifications.subscriptions import (
    SubscriptionRecord,
)


class DeviceAttemptRecord(Base):
    __tablename__ = "student_notification_device_attempts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["delivery_id", "account_id"],
            [
                "student_notification_deliveries.id",
                "student_notification_deliveries.recipient_id",
            ],
        ),
        CheckConstraint("generation BETWEEN 1 AND 3", name="bounded_device_generation"),
        ForeignKeyConstraint(
            ["account_id", "installation_id"],
            [
                "student_notification_subscriptions.account_id",
                "student_notification_subscriptions.installation_id",
            ],
        ),
        CheckConstraint(
            "state IN ('sending','accepted','retryable','rejected','unknown')",
            name="known_device_outcome",
        ),
    )
    delivery_id: Mapped[UUID] = mapped_column(primary_key=True)
    account_id: Mapped[UUID] = mapped_column(primary_key=True)
    installation_id: Mapped[UUID] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(16))
    lease_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    generation: Mapped[int]


@dataclass(frozen=True, slots=True)
class SubscribedPushDelivery:
    sessions: async_sessionmaker[AsyncSession]
    sealer: Fernet = field(repr=False)
    providers: PushProviders

    async def send(self, delivery: Delivery) -> Outcome:
        async with transaction(self.sessions) as session:
            installations = (
                await session.scalars(
                    select(SubscriptionRecord.installation_id)
                    .where(
                        SubscriptionRecord.account_id == delivery.recipient_id,
                        SubscriptionRecord.enabled.is_(True),
                    )
                    .order_by(SubscriptionRecord.installation_id)
                    .limit(8)
                )
            ).all()
        if not installations:
            return Outcome.REJECTED
        outcomes = await asyncio.gather(
            *(self._one(delivery, installation) for installation in installations)
        )
        if Outcome.UNKNOWN in outcomes:
            return Outcome.UNKNOWN
        if Outcome.RETRYABLE in outcomes:
            return Outcome.RETRYABLE  # Accepted devices are durably skipped on the retry.
        return Outcome.ACCEPTED if Outcome.ACCEPTED in outcomes else Outcome.REJECTED

    async def _one(self, delivery: Delivery, installation: UUID) -> Outcome:
        async with transaction(self.sessions) as session:
            account = await session.scalar(
                select(AccountRecord)
                .where(AccountRecord.id == delivery.recipient_id)
                .with_for_update(key_share=True)
            )
            subscription = await session.scalar(
                select(SubscriptionRecord)
                .where(
                    SubscriptionRecord.account_id == delivery.recipient_id,
                    SubscriptionRecord.installation_id == installation,
                )
                .with_for_update()
            )
            if (
                account is None
                or account.deleted_at is not None
                or account.banned_at is not None
                or subscription is None
                or not subscription.enabled
                or subscription.sealed_material is None
            ):
                return Outcome.REJECTED
            # Account lock serializes this authorization with canonical logout.
            # Explicit revocation only: ordinary session expiry policy is unchanged.
            enrollment = await session.get(SessionRecord, subscription.enrolled_session_id)
            if (
                enrollment is None
                or enrollment.account_id != delivery.recipient_id
                or enrollment.revoked_at is not None
            ):
                return Outcome.REJECTED
            now = await clock(session)
            key = (delivery.id, delivery.recipient_id, installation)
            attempt = await session.get(DeviceAttemptRecord, key)
            if attempt is not None and attempt.state != Outcome.RETRYABLE.value:
                # Never replay sending/ambiguous or already accepted endpoints.
                return (
                    Outcome.UNKNOWN
                    if attempt.state in ("sending", "unknown")
                    else Outcome(attempt.state)
                )
            generation = 1 if attempt is None else attempt.generation + 1
            if attempt is None:
                attempt = DeviceAttemptRecord(
                    delivery_id=delivery.id,
                    account_id=delivery.recipient_id,
                    installation_id=installation,
                )
                session.add(attempt)
            attempt.state, attempt.generation, attempt.lease_until = (
                "sending",
                generation,
                now + timedelta(seconds=30),
            )
            material: object = json.loads(self.sealer.decrypt(subscription.sealed_material))
            if not isinstance(material, dict) or not isinstance(material.get("endpoint"), str):
                raise ValueError("Invalid sealed device registration")
            endpoint: object = material["endpoint"]
            if not isinstance(endpoint, str):
                raise ValueError("Invalid sealed endpoint")
            public: object = material.get("p256dh")
            auth: object = material.get("auth")
            if (public is not None and not isinstance(public, str)) or (
                auth is not None and not isinstance(auth, str)
            ):
                raise ValueError("Invalid sealed Web Push key material")
            platform = Platform(subscription.platform)
            await session.flush()
        # No transaction/core/registration lock crosses provider IO.
        result = await self.providers.send(delivery, platform, endpoint, public, auth)
        async with transaction(self.sessions) as session:
            stored = await session.get(DeviceAttemptRecord, key, with_for_update=True)
            if stored is not None and stored.state == "sending" and stored.generation == generation:
                stored.state = result.value
            else:
                # Durable logout fence wins over a late provider response.
                return Outcome.UNKNOWN
        return result
