import hashlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    LargeBinary,
    String,
    UniqueConstraint,
    case,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from studymate.application.idempotency import IntentKey
from studymate.application.student_notifications.subscriptions import (
    SubscriptionIntent,
    SubscriptionVersionError,
)
from studymate.domain.student_notifications.capabilities import (
    DeviceState,
    Platform,
    Registration,
)
from studymate.infrastructure.persistence.base import Base
from studymate.infrastructure.persistence.identity_sessions import (
    SqlIdentityTransaction,
)
from studymate.infrastructure.student_notifications.providers import unb64
from studymate.infrastructure.student_notifications.queue import transaction

MAX_DEVICES = 8
AUTH_BYTES = 16
P256_PUBLIC_BYTES = 65


class SubscriptionRecord(Base):
    __tablename__ = "student_notification_subscriptions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["enrolled_session_id", "account_id"],
            ["sessions.id", "sessions.account_id"],
        ),
        UniqueConstraint("endpoint_digest", name="uq_student_notification_transport_owner"),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint(
            "endpoint_digest IS NULL OR octet_length(endpoint_digest)=32",
            name="endpoint_digest_shape",
        ),
        CheckConstraint("platform IN ('web','ios','android')", name="known_platform"),
        CheckConstraint(
            "(enabled AND sealed_material IS NOT NULL AND endpoint_digest IS NOT NULL) OR "
            "(NOT enabled AND sealed_material IS NULL AND endpoint_digest IS NULL)",
            name="enabled_material",
        ),
    )
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"), primary_key=True)
    installation_id: Mapped[UUID] = mapped_column(primary_key=True)
    enrolled_session_id: Mapped[UUID] = mapped_column()
    platform: Mapped[str] = mapped_column(String(8))
    timezone: Mapped[str | None] = mapped_column(String(100))
    version: Mapped[int]
    enabled: Mapped[bool]
    endpoint_digest: Mapped[bytes | None] = mapped_column(LargeBinary(32))
    sealed_material: Mapped[bytes | None] = mapped_column(LargeBinary)
    material_digest: Mapped[bytes | None] = mapped_column(LargeBinary(32))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SubscriptionIntentRecord(Base):
    __tablename__ = "student_notification_subscription_intents"
    __table_args__ = (
        CheckConstraint("octet_length(fingerprint)=32", name="fingerprint_shape"),
        CheckConstraint("key ~ '^[A-Za-z0-9_-]{8,128}$'", name="intent_key_shape"),
        CheckConstraint("result_version > 0", name="positive_result_version"),
        ForeignKeyConstraint(
            ["account_id", "installation_id"],
            [
                "student_notification_subscriptions.account_id",
                "student_notification_subscriptions.installation_id",
            ],
        ),
    )
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"), primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32))
    installation_id: Mapped[UUID]
    platform: Mapped[str] = mapped_column(String(8))
    result_version: Mapped[int]
    result_enabled: Mapped[bool]
    result_timezone: Mapped[str | None] = mapped_column(String(100))
    result_fingerprint: Mapped[str | None] = mapped_column(String(64))


@dataclass(frozen=True, slots=True)
class SqlSubscriptionTransaction(SqlIdentityTransaction):
    sealer: Fernet = field(repr=False)
    web_hosts: tuple[str, ...]

    async def read(self, account_id: UUID, installation: UUID) -> DeviceState | None:
        row = await self.session.get(SubscriptionRecord, (account_id, installation))
        return (
            None
            if row is None
            else DeviceState(
                row.installation_id,
                Platform(row.platform),
                row.version,
                row.enabled,
                row.timezone,
                None if row.material_digest is None else row.material_digest.hex(),
            )
        )

    async def replay(self, account_id: UUID, key: IntentKey) -> SubscriptionIntent | None:
        row = await self.session.get(SubscriptionIntentRecord, (account_id, key.value))
        return (
            None
            if row is None
            else SubscriptionIntent(
                row.fingerprint,
                DeviceState(
                    row.installation_id,
                    Platform(row.platform),
                    row.result_version,
                    row.result_enabled,
                    row.result_timezone,
                    row.result_fingerprint,
                ),
            )
        )

    async def save(
        self,
        account_id: UUID,
        session_id: UUID,
        value: Registration,
        prior: DeviceState | None,
    ) -> DeviceState:
        from urllib.parse import urlsplit

        # Exact provider-host allowlist closes user-controlled push-endpoint SSRF/redirects.
        if (
            value.enabled
            and value.platform == Platform.WEB
            and urlsplit(value.endpoint or "").hostname not in self.web_hosts
        ):
            raise ValueError("Push endpoint provider is not configured")
        if value.enabled and value.platform == Platform.WEB:
            public, auth = unb64(value.p256dh or ""), unb64(value.auth or "")
            if len(public) != P256_PUBLIC_BYTES or not public.startswith(b"\x04"):
                raise ValueError("Web Push requires uncompressed P-256 public key")
            ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public)
            if len(auth) != AUTH_BYTES:
                raise ValueError("Web Push auth secret must be sixteen bytes")
        row = await self.session.get(SubscriptionRecord, (account_id, value.installation_id))
        if value.enabled and (row is None or not row.enabled):
            # Account lock from canonical identity UoW serializes admissions. Fetch at
            # most eight active IDs; historical tombstones never consume active slots.
            active = (
                await self.session.scalars(
                    select(SubscriptionRecord.installation_id)
                    .where(
                        SubscriptionRecord.account_id == account_id,
                        SubscriptionRecord.enabled.is_(True),
                    )
                    .limit(MAX_DEVICES)
                )
            ).all()
            if len(active) >= MAX_DEVICES:
                raise SubscriptionVersionError
        version = 1 if prior is None else prior.version + 1
        digest = (
            hashlib.sha256((value.platform.value + ":" + (value.endpoint or "")).encode()).digest()
            if value.enabled
            else None
        )
        if digest is not None:
            duplicate = await self.session.scalar(
                select(SubscriptionRecord.account_id).where(
                    SubscriptionRecord.endpoint_digest == digest,
                    (SubscriptionRecord.account_id != account_id)
                    | (SubscriptionRecord.installation_id != value.installation_id),
                )
            )
            if duplicate is not None:
                raise SubscriptionVersionError
        # Unique digest is the final race guard; endpoint ownership never transfers silently.
        material = (
            self.sealer.encrypt(
                json.dumps(
                    {
                        "endpoint": value.endpoint,
                        "p256dh": value.p256dh,
                        "auth": value.auth,
                    }
                ).encode()
            )
            if value.enabled
            else None
        )
        # SQLAlchemy2.1 Core SELECTs also autoflush. Read the clock before creating
        # or mutating a row, so no query can flush a partially populated registration.
        at = await self.now()
        if row is None:
            row = SubscriptionRecord(account_id=account_id, installation_id=value.installation_id)
            self.session.add(row)
        row.enrolled_session_id = session_id
        row.platform, row.timezone, row.version, row.enabled = (
            value.platform.value,
            value.timezone,
            version,
            value.enabled,
        )
        row.endpoint_digest, row.sealed_material, row.updated_at = (
            digest,
            material,
            at,
        )
        row.material_digest = (
            hashlib.sha256(
                "\0".join(
                    (
                        value.platform.value,
                        value.endpoint or "",
                        value.p256dh or "",
                        value.auth or "",
                    )
                ).encode()
            ).digest()
            if value.enabled
            else None
        )
        await self.session.flush()
        return DeviceState(
            value.installation_id,
            value.platform,
            version,
            value.enabled,
            value.timezone,
            None if row.material_digest is None else row.material_digest.hex(),
        )

    async def remember(self, account_id: UUID, key: IntentKey, intent: SubscriptionIntent) -> None:
        result = intent.result
        self.session.add(
            SubscriptionIntentRecord(
                account_id=account_id,
                key=key.value,
                fingerprint=intent.fingerprint,
                installation_id=result.installation_id,
                platform=result.platform.value,
                result_version=result.version,
                result_enabled=result.enabled,
                result_timezone=result.timezone,
                result_fingerprint=result.material_fingerprint,
            )
        )
        await self.session.flush()


@dataclass(frozen=True, slots=True)
class SqlSubscriptionUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    sealer: Fernet = field(repr=False)
    web_hosts: tuple[str, ...]
    shared_identity_locks: bool = False

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlSubscriptionTransaction]:
        try:
            async with transaction(self.sessions, read_only=self.shared_identity_locks) as session:
                yield SqlSubscriptionTransaction(
                    session,
                    self.sealer,
                    self.web_hosts,
                    shared_identity_locks=self.shared_identity_locks,
                )
        except IntegrityError as error:
            if getattr(error.orig, "sqlstate", None) == "23505":
                raise SubscriptionVersionError from None
            raise


async def retire_actor_notifications(session: AsyncSession, account_id: UUID, at: datetime) -> None:
    """Caller owns lifecycle account lock; retire secrets/work in that SAME transaction."""
    from sqlalchemy import update

    from studymate.domain.student_notifications.delivery import State
    from studymate.infrastructure.student_notifications.models import DeliveryRecord

    await session.execute(
        update(SubscriptionRecord)
        .where(SubscriptionRecord.account_id == account_id)
        .values(
            enabled=False,
            sealed_material=None,
            endpoint_digest=None,
            material_digest=None,
            version=SubscriptionRecord.version + 1,
            updated_at=at,
        )
    )
    scope = (DeliveryRecord.recipient_id == account_id) | (DeliveryRecord.actor_id == account_id)
    await session.execute(
        update(DeliveryRecord)
        .where(scope, DeliveryRecord.state.in_((State.PENDING.value, State.CLAIMED.value)))
        .values(state=State.CANCELLED.value, lease_token=None, lease_until=None)
    )
    await session.execute(
        update(DeliveryRecord)
        .where(scope, DeliveryRecord.state == State.SENDING.value)
        .values(state=State.UNKNOWN.value, lease_token=None, lease_until=None)
    )


@dataclass(frozen=True, slots=True)
class SqlInstallationLogoutTransaction(SqlIdentityTransaction):
    async def retire_installation(
        self,
        account_id: UUID,
        session_id: UUID,
        installation_id: UUID | None,
        at: datetime,
    ) -> bool:
        from sqlalchemy import update

        from studymate.infrastructure.student_notifications.capabilities import (
            DeviceAttemptRecord,
        )

        # Canonical Logout owns account then session locks. Retire by authenticated
        # session, never by a browser's ability to retain its technical installation ID.
        scope = (
            SubscriptionRecord.account_id == account_id,
            SubscriptionRecord.enrolled_session_id == session_id,
        )
        requested_matches = (
            installation_id is not None
            and await self.session.scalar(
                select(SubscriptionRecord.installation_id).where(
                    *scope, SubscriptionRecord.installation_id == installation_id
                )
            )
            is not None
        )
        installations = (
            await self.session.scalars(
                update(SubscriptionRecord)
                .where(*scope, SubscriptionRecord.enabled.is_(True))
                .values(
                    enabled=False,
                    sealed_material=None,
                    endpoint_digest=None,
                    material_digest=None,
                    version=SubscriptionRecord.version + 1,
                    updated_at=at,
                )
                .returning(SubscriptionRecord.installation_id)
            )
        ).all()
        if installations:
            await self.session.execute(
                update(DeviceAttemptRecord)
                .where(
                    DeviceAttemptRecord.account_id == account_id,
                    DeviceAttemptRecord.installation_id.in_(installations),
                    DeviceAttemptRecord.state.in_(("sending", "retryable")),
                )
                .values(
                    state=case(
                        (DeviceAttemptRecord.state == "sending", "unknown"),
                        else_="rejected",
                    ),
                    lease_until=at,
                )
            )
        await self.session.flush()
        # Optional HTTP acknowledgement remains scoped to the requested installation.
        return requested_matches


@dataclass(frozen=True, slots=True)
class SqlInstallationLogoutUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlInstallationLogoutTransaction]:
        async with transaction(self.sessions) as session:
            yield SqlInstallationLogoutTransaction(session)
