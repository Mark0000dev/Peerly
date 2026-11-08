from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import DateTime, cast, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.identity.email_verification import (
    DeliveryBudget,
    EmailDeliveryState,
    EmailIntent,
    EmailOperation,
    EmailTransaction,
    StoredChallenge,
    VerificationOutcome,
    VerificationResult,
)
from studymate.domain.identity import StudentEmail
from studymate.domain.membership import MAX_CODE_ATTEMPTS, EmailChallenge
from studymate.infrastructure.observability.tracing import current_origin
from studymate.infrastructure.persistence.email_models import (
    EmailChallengeRecord,
    EmailDeliveryRecord,
    EmailIntentRecord,
)
from studymate.infrastructure.persistence.identity_models import InstitutionalBindingRecord
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.product_events import record_membership_event
from studymate.infrastructure.persistence.transactions import open_transaction


def _stored(record: EmailChallengeRecord) -> StoredChallenge:
    return StoredChallenge(
        EmailChallenge(
            record.id,
            record.account_id,
            record.session_id,
            StudentEmail(record.email),
            record.created_at,
            record.expires_at,
            record.resend_at,
            record.attempts,
            record.consumed_at,
            record.superseded_at,
        ),
        record.code_digest,
    )


@dataclass(frozen=True, slots=True)
class SqlEmailTransaction(SqlIdentityTransaction):
    async def intent(
        self, account_id: UUID, operation: EmailOperation, key: IntentKey
    ) -> EmailIntent | None:
        record = await self.session.get(EmailIntentRecord, (account_id, operation.value, key.value))
        if record is None:
            return None
        result = None
        if record.outcome is not None:
            if record.attempts_remaining is None:
                raise RuntimeError("Stored verification result has no attempt count")
            result = VerificationResult(
                VerificationOutcome(record.outcome), record.attempts_remaining, record.verified_at
            )
        return EmailIntent(record.fingerprint, record.challenge_id, result)

    async def remember_intent(
        self, account_id: UUID, operation: EmailOperation, key: IntentKey, intent: EmailIntent
    ) -> None:
        result = intent.result
        self.session.add(
            EmailIntentRecord(
                account_id=account_id,
                operation=operation.value,
                key=key.value,
                fingerprint=intent.fingerprint,
                challenge_id=intent.challenge_id,
                outcome=result.outcome.value if result is not None else None,
                attempts_remaining=result.attempts_remaining if result is not None else None,
                verified_at=result.verified_at if result is not None else None,
            )
        )
        await self.session.flush()

    async def lock_budget(
        self, account_id: UUID, email: StudentEmail, source: bytes, since: datetime
    ) -> DeliveryBudget:
        keys = sorted((f"account:{account_id}", f"address:{email.value}", f"source:{source.hex()}"))
        for key in keys:
            await self.session.execute(
                select(func.pg_advisory_xact_lock(func.hashtextextended(key, 2)))
            )
        return await self.read_budget(account_id, email, source, since)

    async def read_budget(
        self,
        account_id: UUID,
        email: StudentEmail,
        source: bytes,
        since: datetime,
    ) -> DeliveryBudget:
        account = EmailChallengeRecord.account_id == account_id
        address = EmailChallengeRecord.email == email.value
        source_match = EmailChallengeRecord.source_digest == source
        statement = (
            select(
                func.count().filter(account),
                func.count().filter(address),
                func.count().filter(source_match),
                cast(
                    func.coalesce(func.min(EmailChallengeRecord.created_at).filter(account), since),
                    DateTime(timezone=True),
                ),
                cast(
                    func.coalesce(func.min(EmailChallengeRecord.created_at).filter(address), since),
                    DateTime(timezone=True),
                ),
                cast(
                    func.coalesce(
                        func.min(EmailChallengeRecord.created_at).filter(source_match), since
                    ),
                    DateTime(timezone=True),
                ),
            )
            .select_from(EmailChallengeRecord)
            .where(EmailChallengeRecord.created_at >= since, or_(account, address, source_match))
        )
        a, b, c, first_account, first_address, first_source = (
            await self.session.execute(statement)
        ).one()
        return DeliveryBudget(
            a,
            b,
            c,
            first_account + timedelta(hours=1),
            first_address + timedelta(hours=1),
            first_source + timedelta(hours=1),
        )

    async def delivery_state(self, challenge_id: UUID) -> EmailDeliveryState:
        status = (
            await self.session.scalars(
                select(EmailDeliveryRecord.status).where(
                    EmailDeliveryRecord.challenge_id == challenge_id
                )
            )
        ).one()
        return {
            "queued": EmailDeliveryState.QUEUED,
            "inflight": EmailDeliveryState.SENDING,
            "delivered": EmailDeliveryState.SENT,
            "failed": EmailDeliveryState.FAILED,
            "cancelled": EmailDeliveryState.CANCELLED,
        }[status]

    async def terminal_outcome(self, challenge_id: UUID) -> VerificationOutcome | None:
        outcome = (
            await self.session.scalars(
                select(EmailIntentRecord.outcome).where(
                    EmailIntentRecord.challenge_id == challenge_id,
                    EmailIntentRecord.operation == EmailOperation.VERIFY.value,
                    EmailIntentRecord.outcome.in_(
                        (
                            VerificationOutcome.VERIFIED.value,
                            VerificationOutcome.SUPPORT_REQUIRED.value,
                        )
                    ),
                )
            )
        ).one_or_none()
        return VerificationOutcome(outcome) if outcome is not None else None

    async def current_challenge(self, account_id: UUID) -> StoredChallenge | None:
        record = (
            await self.session.scalars(
                select(EmailChallengeRecord)
                .where(
                    EmailChallengeRecord.account_id == account_id,
                    EmailChallengeRecord.consumed_at.is_(None),
                    EmailChallengeRecord.superseded_at.is_(None),
                )
                .with_for_update()
            )
        ).one_or_none()
        return _stored(record) if record is not None else None

    async def lock_challenge(self, challenge_id: UUID) -> StoredChallenge | None:
        record = await self.session.get(EmailChallengeRecord, challenge_id, with_for_update=True)
        return _stored(record) if record is not None else None

    async def add_challenge(self, challenge: EmailChallenge, digest: bytes, source: bytes) -> None:
        self.session.add(
            EmailChallengeRecord(
                id=challenge.id,
                account_id=challenge.account_id,
                session_id=challenge.session_id,
                email=challenge.email.value,
                code_digest=digest,
                source_digest=source,
                created_at=challenge.created_at,
                expires_at=challenge.expires_at,
                resend_at=challenge.resend_at,
                attempts=challenge.attempts,
                consumed_at=challenge.consumed_at,
                superseded_at=challenge.superseded_at,
            )
        )
        await self.session.flush()

    async def save_challenge(self, challenge: EmailChallenge) -> None:
        statement = (
            update(EmailChallengeRecord)
            .where(EmailChallengeRecord.id == challenge.id)
            .values(
                attempts=challenge.attempts,
                consumed_at=challenge.consumed_at,
                superseded_at=challenge.superseded_at,
            )
        )
        if (
            challenge.consumed_at is not None
            or challenge.superseded_at is not None
            or challenge.attempts == MAX_CODE_ATTEMPTS
        ):
            statement = statement.values(code_digest=None)
        await self.session.execute(statement)

    async def enqueue_email(self, challenge_id: UUID, sealed: bytes, at: datetime) -> None:
        origin = current_origin()
        self.session.add(
            EmailDeliveryRecord(
                id=uuid4(),
                challenge_id=challenge_id,
                status="queued",
                sealed_envelope=sealed,
                created_at=at,
                due_at=at,
                attempts=0,
                lease_generation=0,
                origin_request_id=origin.request_id if origin is not None else None,
                origin_action_id=origin.action_id if origin is not None else None,
                origin_trace_id=origin.trace_id if origin is not None else None,
                origin_span_id=origin.span_id if origin is not None else None,
            )
        )
        await self.session.flush()

    async def cancel_email(self, challenge_id: UUID) -> None:
        await self.session.execute(
            update(EmailDeliveryRecord)
            .where(
                EmailDeliveryRecord.challenge_id == challenge_id,
                EmailDeliveryRecord.status.in_(("queued", "inflight")),
            )
            .values(status="cancelled", sealed_envelope=None, lease_until=None)
        )

    async def bind_membership(self, account_id: UUID, email: StudentEmail, at: datetime) -> bool:
        statement = (
            insert(InstitutionalBindingRecord)
            .values(
                account_id=account_id,
                email=email.value,
                verified_at=at,
            )
            .on_conflict_do_nothing()
            .returning(InstitutionalBindingRecord.account_id)
        )
        bound = (await self.session.scalars(statement)).one_or_none() is not None
        if bound:
            await record_membership_event(self.session, account_id, at)
        return bound


@dataclass(frozen=True, slots=True)
class SqlEmailUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[EmailTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlEmailTransaction(session)
