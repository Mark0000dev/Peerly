from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, cast, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.identity.sessions import (
    IdentitySnapshot,
    IdentityTransaction,
)
from studymate.domain.identity import Session, StudentEmail
from studymate.domain.membership import Membership
from studymate.infrastructure.observability.tracing import record_authenticated_actor
from studymate.infrastructure.persistence.email_models import EmailChallengeRecord
from studymate.infrastructure.persistence.identity_claims import identity_lineage_banned
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
    SessionRecord,
)
from studymate.infrastructure.persistence.onboarding_models import ProfileActivationRecord
from studymate.infrastructure.persistence.registration_reads import read_receipt
from studymate.infrastructure.persistence.transactions import open_transaction


@dataclass(frozen=True, slots=True)
class SqlIdentityTransaction:
    session: AsyncSession

    def authenticated(self, account_id: UUID) -> None:
        record_authenticated_actor(account_id)

    async def lock_identity(self, secret_digest: bytes) -> IdentitySnapshot | None:
        return await self._lock_identity(secret_digest, None)

    async def lock_identity_for_peer(
        self, secret_digest: bytes, peer_id: UUID
    ) -> IdentitySnapshot | None:
        return await self._lock_identity(secret_digest, peer_id)

    async def _lock_identity(
        self, secret_digest: bytes, peer_id: UUID | None
    ) -> IdentitySnapshot | None:
        # This lookup supplies lock scope only; authority is re-read under locks below.
        account_id = await self.session.scalar(
            select(SessionRecord.account_id).where(SessionRecord.secret_digest == secret_digest)
        )
        if account_id is None:
            return None
        participants = (account_id,) if peer_id is None else (account_id, peer_id)
        # Every identity transaction takes account locks before session locks. Social
        # transactions take both accounts in UUID order, including reciprocal actions.
        await self.session.execute(
            select(AccountRecord.id)
            .where(AccountRecord.id.in_(participants))
            .order_by(AccountRecord.id)
            .with_for_update(key_share=True)
        )
        statement = (
            select(SessionRecord, AccountRecord)
            .join(AccountRecord, AccountRecord.id == SessionRecord.account_id)
            .where(
                SessionRecord.secret_digest == secret_digest,
                SessionRecord.account_id == account_id,
            )
            .with_for_update(of=SessionRecord, key_share=True)
        )
        row = (await self.session.execute(statement)).one_or_none()
        if row is None:
            return None
        stored, account = row
        binding = await self.session.get(InstitutionalBindingRecord, account.id)
        membership = (
            Membership(StudentEmail(binding.email), binding.verified_at, binding.revoked_at)
            if binding is not None
            else None
        )
        pending_challenge = None
        if binding is None and account.banned_at is None and account.deleted_at is None:
            pending_challenge = (
                await self.session.scalars(
                    select(EmailChallengeRecord.id)
                    .where(
                        EmailChallengeRecord.account_id == account.id,
                        EmailChallengeRecord.session_id == stored.id,
                        EmailChallengeRecord.superseded_at.is_(None),
                    )
                    .order_by(
                        EmailChallengeRecord.created_at.desc(), EmailChallengeRecord.id.desc()
                    )
                    .limit(1)
                )
            ).one_or_none()
        return IdentitySnapshot(
            session=Session(
                stored.id, stored.account_id, stored.issued_at, stored.expires_at, stored.revoked_at
            ),
            membership=membership,
            banned=account.banned_at is not None
            or await identity_lineage_banned(self.session, account.id),
            deleted_at=account.deleted_at,
            registration=await read_receipt(self.session, account.id),
            email_challenge_id=pending_challenge,
            activation_complete=(
                await self.session.scalar(
                    select(ProfileActivationRecord.account_id).where(
                        ProfileActivationRecord.account_id == account.id
                    )
                )
            )
            is not None,
        )

    async def now(self) -> datetime:
        # Read after acquiring locks: transaction-start time can be stale after waiting.
        return (
            await self.session.scalars(
                select(cast(func.clock_timestamp(), DateTime(timezone=True)))
            )
        ).one()

    async def revoke_session(self, session_id: UUID, at: datetime) -> None:
        await self.session.execute(
            update(SessionRecord).where(SessionRecord.id == session_id).values(revoked_at=at)
        )


@dataclass(frozen=True, slots=True)
class SqlPeerIdentityTransaction(SqlIdentityTransaction):
    peer_id: UUID

    async def lock_identity(self, secret_digest: bytes) -> IdentitySnapshot | None:
        return await self.lock_identity_for_peer(secret_digest, self.peer_id)


@dataclass(frozen=True, slots=True)
class SqlIdentityUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[IdentityTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlIdentityTransaction(session)
