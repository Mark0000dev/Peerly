"""One bounded joined read of safe columns; secrets are never loaded or serialized."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import load_only

from studymate.application.operator.email_history_ports import EmailHistoryWindow
from studymate.domain.operator.email_history import (
    EMAIL_HISTORY_PAGE_SIZE,
    EmailHistoryChallenge,
    EmailHistoryDelivery,
    EmailHistoryManualVerification,
    StoredEmailDeliveryError,
    StoredEmailDeliveryStatus,
)
from studymate.infrastructure.operator.membership_verification_models import (
    OperatorMembershipVerificationRecord,
)
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.email_models import (
    EmailChallengeRecord,
    EmailDeliveryRecord,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.transactions import open_transaction


def delivery_value(row: EmailDeliveryRecord | None) -> EmailHistoryDelivery | None:
    if row is None:
        return None
    return EmailHistoryDelivery(
        row.id,
        StoredEmailDeliveryStatus(row.status),
        row.created_at,
        row.due_at,
        row.attempts,
        row.delivered_at,
        StoredEmailDeliveryError(row.last_error) if row.last_error is not None else None,
        row.origin_request_id,
        row.origin_action_id,
        row.origin_trace_id,
        row.origin_span_id,
    )


def manual_value(
    row: OperatorMembershipVerificationRecord | None,
) -> EmailHistoryManualVerification | None:
    if row is None:
        return None
    return EmailHistoryManualVerification(
        row.id, row.operator_id, row.operator_access_version, row.event_id, row.verified_at
    )


@dataclass(frozen=True, slots=True)
class SqlOperatorEmailHistoryTransaction(SqlOperatorTransaction):
    async def email_history_account_exists(self, account_id: UUID) -> bool:
        self.checked_access()
        return (
            await self.session.scalar(
                select(AccountRecord.id).where(AccountRecord.id == account_id)
            )
            is not None
        )

    async def email_history_challenges(
        self, account_id: UUID, window: EmailHistoryWindow
    ) -> tuple[EmailHistoryChallenge, ...]:
        self.checked_access()
        challenge, delivery, manual = (
            EmailChallengeRecord,
            EmailDeliveryRecord,
            OperatorMembershipVerificationRecord,
        )
        statement = (
            select(challenge, delivery, manual)
            .outerjoin(delivery, delivery.challenge_id == challenge.id)
            .outerjoin(
                manual,
                (manual.challenge_id == challenge.id) & (manual.account_id == challenge.account_id),
            )
            .where(challenge.account_id == account_id, challenge.created_at <= window.as_of)
            .options(
                load_only(
                    challenge.id,
                    challenge.account_id,
                    challenge.session_id,
                    challenge.email,
                    challenge.created_at,
                    challenge.expires_at,
                    challenge.resend_at,
                    challenge.attempts,
                    challenge.consumed_at,
                    challenge.superseded_at,
                    raiseload=True,
                ),
                load_only(
                    delivery.id,
                    delivery.challenge_id,
                    delivery.status,
                    delivery.created_at,
                    delivery.due_at,
                    delivery.attempts,
                    delivery.delivered_at,
                    delivery.last_error,
                    delivery.origin_request_id,
                    delivery.origin_action_id,
                    delivery.origin_trace_id,
                    delivery.origin_span_id,
                    raiseload=True,
                ),
                load_only(
                    manual.id,
                    manual.operator_id,
                    manual.operator_access_version,
                    manual.event_id,
                    manual.verified_at,
                    raiseload=True,
                ),
            )
        )
        if window.before is not None:
            statement = statement.where(
                tuple_(challenge.created_at, challenge.id)
                < tuple_(window.before.created_at, window.before.challenge_id)
            )
        rows = await self.session.execute(
            statement.order_by(challenge.created_at.desc(), challenge.id.desc()).limit(
                EMAIL_HISTORY_PAGE_SIZE + 1
            )
        )
        return tuple(
            EmailHistoryChallenge(
                row.id,
                row.account_id,
                row.session_id,
                row.email,
                row.created_at,
                row.expires_at,
                row.resend_at,
                row.attempts,
                row.consumed_at,
                row.superseded_at,
                delivery_value(outbox),
                manual_value(proof),
            )
            for row, outbox, proof in rows
        )


@dataclass(frozen=True, slots=True)
class SqlOperatorEmailHistoryUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: OperatorAuditRecorder

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlOperatorEmailHistoryTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlOperatorEmailHistoryTransaction(session, self.recorder)
