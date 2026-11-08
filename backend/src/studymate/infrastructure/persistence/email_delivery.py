from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, and_, case, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.identity.email_delivery import (
    MAX_DELIVERY_ATTEMPTS,
    DeliveryResolution,
    DeliveryStatus,
    EmailLease,
    EmailWorkerTransaction,
)
from studymate.domain.membership import MAX_CODE_ATTEMPTS
from studymate.infrastructure.observability.email import record_delivery
from studymate.infrastructure.observability.origin import ExecutionOrigin
from studymate.infrastructure.persistence.email_models import (
    EmailChallengeRecord,
    EmailDeliveryRecord,
)
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
    LoginFlowRecord,
    SessionRecord,
)
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.transactions import open_transaction


def _valid_challenges(at: datetime) -> Select[UUID]:
    bound = (
        select(InstitutionalBindingRecord.account_id)
        .where(
            InstitutionalBindingRecord.account_id == EmailChallengeRecord.account_id,
        )
        .exists()
    )
    return (
        select(EmailChallengeRecord.id)
        .join(SessionRecord, SessionRecord.id == EmailChallengeRecord.session_id)
        .join(AccountRecord, AccountRecord.id == EmailChallengeRecord.account_id)
        .where(
            EmailChallengeRecord.consumed_at.is_(None),
            EmailChallengeRecord.superseded_at.is_(None),
            EmailChallengeRecord.code_digest.is_not(None),
            EmailChallengeRecord.expires_at > at,
            EmailChallengeRecord.attempts < MAX_CODE_ATTEMPTS,
            SessionRecord.issued_at <= at,
            SessionRecord.expires_at > at,
            SessionRecord.revoked_at.is_(None),
            AccountRecord.banned_at.is_(None),
            AccountRecord.deleted_at.is_(None),
            ~bound,
        )
    )


@dataclass(frozen=True, slots=True)
class SqlEmailWorkerTransaction(SqlIdentityTransaction):
    async def cleanup(self, at: datetime, batch: int) -> None:
        expired_codes = (
            select(EmailChallengeRecord.id)
            .where(
                EmailChallengeRecord.expires_at <= at,
                EmailChallengeRecord.code_digest.is_not(None),
            )
            .limit(batch)
            .with_for_update(skip_locked=True)
        )
        await self.session.execute(
            update(EmailChallengeRecord)
            .where(
                EmailChallengeRecord.id.in_(expired_codes),
            )
            .values(code_digest=None)
        )
        expired_logins = (
            select(LoginFlowRecord.id)
            .where(
                LoginFlowRecord.expires_at <= at,
                LoginFlowRecord.sealed_material.is_not(None),
            )
            .limit(batch)
            .with_for_update(skip_locked=True)
        )
        await self.session.execute(
            update(LoginFlowRecord)
            .where(
                LoginFlowRecord.id.in_(expired_logins),
            )
            .values(consumed_at=at, sealed_material=None)
        )
        exhausted = and_(
            EmailDeliveryRecord.attempts >= MAX_DELIVERY_ATTEMPTS,
            or_(EmailDeliveryRecord.status == "queued", EmailDeliveryRecord.lease_until <= at),
        )
        invalid = (
            select(EmailDeliveryRecord.id)
            .where(
                EmailDeliveryRecord.status.in_(("queued", "inflight")),
                or_(EmailDeliveryRecord.challenge_id.not_in(_valid_challenges(at)), exhausted),
            )
            .limit(batch)
            .with_for_update(skip_locked=True)
        )
        await self.session.execute(
            update(EmailDeliveryRecord)
            .where(
                EmailDeliveryRecord.id.in_(invalid),
            )
            .values(
                status=case((exhausted, "failed"), else_="cancelled"),
                sealed_envelope=None,
                lease_until=None,
                last_error=case((exhausted, "provider_unavailable"), else_=None),
            )
        )

    async def claim(self, at: datetime, lease_until: datetime) -> EmailLease | None:
        row = (
            await self.session.execute(
                select(EmailDeliveryRecord, EmailChallengeRecord.account_id)
                .join(
                    EmailChallengeRecord,
                    EmailChallengeRecord.id == EmailDeliveryRecord.challenge_id,
                )
                .where(
                    EmailDeliveryRecord.attempts < MAX_DELIVERY_ATTEMPTS,
                    or_(
                        and_(
                            EmailDeliveryRecord.status == "queued", EmailDeliveryRecord.due_at <= at
                        ),
                        and_(
                            EmailDeliveryRecord.status == "inflight",
                            EmailDeliveryRecord.lease_until <= at,
                        ),
                    ),
                )
                .order_by(EmailDeliveryRecord.due_at, EmailDeliveryRecord.id)
                .limit(1)
                .with_for_update(of=EmailDeliveryRecord, skip_locked=True)
            )
        ).one_or_none()
        if row is None:
            return None
        record, account_id = row
        if record.sealed_envelope is None:
            raise RuntimeError("Live email delivery has no encrypted envelope")
        record.status = "inflight"
        record.attempts += 1
        record.lease_generation += 1
        record.lease_until = lease_until
        await self.session.flush()
        origin = (
            ExecutionOrigin(
                record.origin_request_id,
                record.origin_action_id,
                record.origin_trace_id,
                record.origin_span_id,
            )
            if record.origin_request_id is not None
            else None
        )
        record_delivery(record.id, account_id, record.attempts, origin)
        return EmailLease(
            record.id,
            record.challenge_id,
            record.lease_generation,
            record.attempts,
            record.sealed_envelope,
        )

    async def is_current(self, lease: EmailLease, at: datetime) -> bool:
        current = (
            select(EmailDeliveryRecord.id)
            .where(
                EmailDeliveryRecord.id == lease.id,
                EmailDeliveryRecord.status == "inflight",
                EmailDeliveryRecord.lease_generation == lease.generation,
                EmailDeliveryRecord.lease_until > at,
                EmailDeliveryRecord.challenge_id.in_(_valid_challenges(at)),
            )
            .exists()
        )
        return (await self.session.scalars(select(current))).one()

    async def finish(self, lease: EmailLease, resolution: DeliveryResolution, at: datetime) -> bool:
        statement = (
            update(EmailDeliveryRecord)
            .where(
                EmailDeliveryRecord.id == lease.id,
                EmailDeliveryRecord.status == "inflight",
                EmailDeliveryRecord.lease_generation == lease.generation,
            )
            .values(
                status="queued"
                if resolution.status == DeliveryStatus.RETRY
                else resolution.status.value,
                lease_until=None,
                last_error=resolution.error,
            )
        )
        if resolution.status == DeliveryStatus.RETRY:
            if resolution.retry_at is None:
                raise ValueError("A delivery retry must have a deadline")
            statement = statement.values(due_at=resolution.retry_at)
        else:
            statement = statement.values(sealed_envelope=None)
        if resolution.status == DeliveryStatus.DELIVERED:
            statement = statement.values(delivered_at=at)
        return (
            await self.session.scalars(statement.returning(EmailDeliveryRecord.id))
        ).one_or_none() is not None


@dataclass(frozen=True, slots=True)
class SqlEmailWorkerUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[EmailWorkerTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlEmailWorkerTransaction(session)
