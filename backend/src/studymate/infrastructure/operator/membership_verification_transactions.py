"""Short ordered locks and real unique membership binding; no provider/mail/activation."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy import and_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import IdentitySnapshot
from studymate.application.operator.membership_verification_ports import ManualMembershipIntent
from studymate.domain.identity import StudentEmail
from studymate.domain.operator.access import OperatorAccess
from studymate.domain.operator.membership_verification import (
    ManualMembershipVerification,
    ManualVerificationTarget,
    SubmittedInstitutionalEmail,
)
from studymate.infrastructure.operator.membership_verification_models import (
    OperatorMembershipIntentRecord,
    OperatorMembershipVerificationRecord,
)
from studymate.infrastructure.operator.models import OperatorAccessRevisionRecord
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.email_models import (
    EmailChallengeRecord,
    EmailDeliveryRecord,
)
from studymate.infrastructure.persistence.identity_claims import (
    email_lineage_banned,
    identity_lineage_banned,
)
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
    InstitutionalBindingRecord,
)
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.transactions import open_transaction


class ManualMembershipEventRecorder(Protocol):
    async def __call__(self, session: AsyncSession, source: ManualMembershipVerification) -> None:
        """Main records EXACT source.event_id/account/time/smv1c occurrence + change outbox.

        No OTP consumption, foreground activity, implied activation or inspection write.
        Same transaction BEFORE source FK flush; source retained in business DB.
        """
        ...


def verification_value(
    row: OperatorMembershipVerificationRecord, grant: OperatorAccessRevisionRecord
) -> ManualMembershipVerification:
    return ManualMembershipVerification(
        row.id,
        row.account_id,
        row.google_identity_id,
        row.challenge_id,
        OperatorAccess(grant.account_id, grant.version, grant.active, grant.changed_at),
        row.actor_session_id,
        row.event_id,
        StudentEmail(row.email),
        row.verified_at,
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class SqlManualMembershipTransaction(SqlOperatorTransaction):
    target_account_id: UUID
    membership_recorder: ManualMembershipEventRecorder

    async def lock_identity(self, secret_digest: bytes) -> IdentitySnapshot | None:
        return await self.lock_identity_for_peer(secret_digest, self.target_account_id)

    async def verification(self, account_id: UUID) -> ManualMembershipVerification | None:
        self.checked_access()
        result = (
            await self.session.execute(
                select(OperatorMembershipVerificationRecord, OperatorAccessRevisionRecord)
                .join(
                    OperatorAccessRevisionRecord,
                    and_(
                        OperatorAccessRevisionRecord.account_id
                        == OperatorMembershipVerificationRecord.operator_id,
                        OperatorAccessRevisionRecord.version
                        == OperatorMembershipVerificationRecord.operator_access_version,
                    ),
                )
                .where(OperatorMembershipVerificationRecord.account_id == account_id)
            )
        ).one_or_none()
        return verification_value(*result) if result is not None else None

    async def verification_target(self, account_id: UUID) -> ManualVerificationTarget | None:
        self.checked_access()
        if account_id != self.target_account_id:
            raise RuntimeError("Manual membership target differs from actual ordered lock scope")
        account = await self.session.get(AccountRecord, account_id)
        if account is None:
            return None
        identity = await self.session.scalar(
            select(ExternalIdentityRecord.id).where(
                ExternalIdentityRecord.account_id == account_id,
                ExternalIdentityRecord.retired_at.is_(None),
            )
        )
        challenge = (
            await self.session.execute(
                select(
                    EmailChallengeRecord.id,
                    EmailChallengeRecord.account_id,
                    EmailChallengeRecord.email,
                    EmailChallengeRecord.created_at,
                    EmailChallengeRecord.expires_at,
                    EmailChallengeRecord.consumed_at,
                    EmailChallengeRecord.superseded_at,
                )
                .where(EmailChallengeRecord.account_id == account_id)
                .order_by(EmailChallengeRecord.created_at.desc(), EmailChallengeRecord.id.desc())
                .limit(1)
                .with_for_update()
            )
        ).one_or_none()
        submitted = (
            SubmittedInstitutionalEmail(
                challenge.id,
                challenge.account_id,
                StudentEmail(challenge.email),
                challenge.created_at,
                challenge.expires_at,
                challenge.consumed_at,
                challenge.superseded_at,
            )
            if challenge is not None
            else None
        )
        return ManualVerificationTarget(
            account_id,
            identity,
            account.deleted_at is not None,
            account.banned_at is not None,
            await identity_lineage_banned(self.session, account_id),
            await self.session.get(InstitutionalBindingRecord, account_id) is not None,
            submitted,
            await self.verification(account_id),
        )

    async def prior_manual_verification(
        self, operator_id: UUID, key: IntentKey
    ) -> ManualMembershipIntent | None:
        access = self.checked_access()
        if access.account_id != operator_id:
            raise RuntimeError("Manual intent actor differs from current operator")
        intent = await self.session.get(OperatorMembershipIntentRecord, (operator_id, key.value))
        if intent is None:
            return None
        row = await self.session.get(OperatorMembershipVerificationRecord, intent.verification_id)
        if row is None:
            raise RuntimeError("Manual intent lost its retained actual source")
        source = await self.verification(row.account_id)
        if source is None:
            raise RuntimeError("Manual intent lost its actual historical grant")
        return ManualMembershipIntent(intent.fingerprint, source)

    async def apply_manual_verification(
        self,
        source: ManualMembershipVerification,
        email: StudentEmail,
        key: IntentKey,
        fingerprint: bytes,
    ) -> bool:
        access = self.checked_access()
        if (
            source.operator != access
            or source.account_id != self.target_account_id
            or source.email != email
        ):
            raise RuntimeError("Manual write differs from its actual operator/ordered target/email")
        if await email_lineage_banned(self.session, email.value):
            return False
        bound = await self.session.scalar(
            insert(InstitutionalBindingRecord)
            .values(account_id=source.account_id, email=email.value, verified_at=source.verified_at)
            .on_conflict_do_nothing()
            .returning(InstitutionalBindingRecord.account_id)
        )
        if bound is None:
            return False
        updated = await self.session.scalar(
            update(EmailChallengeRecord)
            .where(
                EmailChallengeRecord.id == source.challenge_id,
                EmailChallengeRecord.account_id == source.account_id,
                EmailChallengeRecord.email == email.value,
                EmailChallengeRecord.consumed_at.is_(None),
                EmailChallengeRecord.superseded_at.is_(None),
            )
            .values(superseded_at=source.verified_at, code_digest=None)
            .returning(EmailChallengeRecord.id)
        )
        if updated is None:
            raise RuntimeError("Manual write lost its actual locked pending submission")
        await self.session.execute(
            update(EmailDeliveryRecord)
            .where(
                EmailDeliveryRecord.challenge_id == source.challenge_id,
                EmailDeliveryRecord.status.in_(("queued", "inflight")),
            )
            .values(status="cancelled", sealed_envelope=None, lease_until=None)
        )
        await self.membership_recorder(self.session, source)
        await self.session.flush()
        self.session.add(
            OperatorMembershipVerificationRecord(
                id=source.id,
                account_id=source.account_id,
                google_identity_id=source.google_identity_id,
                challenge_id=source.challenge_id,
                email=email.value,
                operator_id=access.account_id,
                operator_access_version=access.version,
                operator_access_active=True,
                actor_session_id=source.actor_session_id,
                event_id=source.event_id,
                event_kind="auth.email_confirmed",
                verified_at=source.verified_at,
            )
        )
        await self.session.flush()
        self.session.add(
            OperatorMembershipIntentRecord(
                operator_id=access.account_id,
                key=key.value,
                verification_id=source.id,
                fingerprint=fingerprint,
            )
        )
        await self.session.flush()
        return True


@dataclass(frozen=True, slots=True)
class SqlManualMembershipUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: OperatorAuditRecorder
    membership_recorder: ManualMembershipEventRecorder

    @asynccontextmanager
    async def transaction(
        self, actor_secret_digest: bytes, target_account_id: UUID
    ) -> AsyncIterator[SqlManualMembershipTransaction]:
        async with open_transaction(self.sessions) as session:
            await SqlIdentityTransaction(session).lock_identity_for_peer(
                actor_secret_digest, target_account_id
            )
            yield SqlManualMembershipTransaction(
                session,
                self.recorder,
                target_account_id=target_account_id,
                membership_recorder=self.membership_recorder,
            )
