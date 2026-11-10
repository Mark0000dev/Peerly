from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, cast, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.identity.login import (
    CallbackBudget,
    GoogleAccount,
    LoginFlow,
    LoginTransaction,
)
from studymate.domain.identity import Session
from studymate.domain.membership import GoogleIdentity
from studymate.infrastructure.persistence.callback_models import CallbackAttemptRecord
from studymate.infrastructure.persistence.discovery_exposure import record_foreground_activity
from studymate.infrastructure.persistence.identity_claims import (
    identity_lineage_banned,
    retire_deleted_claims,
)
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
    LoginFlowRecord,
    SessionRecord,
)
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.transactions import open_transaction


def _flow(record: LoginFlowRecord) -> LoginFlow:
    return LoginFlow(
        record.id,
        record.state_digest,
        record.browser_digest,
        record.sealed_material,
        record.return_to,
        record.created_at,
        record.expires_at,
        record.consumed_at,
        record.completed_at,
    )


@dataclass(frozen=True, slots=True)
class SqlLoginTransaction(SqlIdentityTransaction):
    async def lock_callback_budget(self, source_digest: bytes, since: datetime) -> CallbackBudget:
        await self.session.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(source_digest.hex(), 3)))
        )
        used, first_attempt = (
            await self.session.execute(
                select(
                    func.count(),
                    cast(func.min(CallbackAttemptRecord.started_at), DateTime(timezone=True)),
                )
                .select_from(CallbackAttemptRecord)
                .where(
                    CallbackAttemptRecord.source_digest == source_digest,
                    CallbackAttemptRecord.started_at >= since,
                    CallbackAttemptRecord.succeeded_at.is_(None),
                )
            )
        ).one()
        return CallbackBudget(used, first_attempt)

    async def add_callback_attempt(
        self, attempt_id: UUID, source_digest: bytes, at: datetime
    ) -> None:
        self.session.add(
            CallbackAttemptRecord(id=attempt_id, source_digest=source_digest, started_at=at)
        )
        await self.session.flush()

    async def succeed_callback(self, attempt_id: UUID, account_id: UUID, at: datetime) -> None:
        await self.session.execute(
            update(CallbackAttemptRecord)
            .where(CallbackAttemptRecord.id == attempt_id)
            .values(succeeded_at=at, account_id=account_id)
        )
        self.authenticated(account_id)

    async def lock_start_budget(self, source_digest: bytes, since: datetime) -> int:
        await self.session.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(source_digest.hex(), 1)))
        )
        return (
            await self.session.scalars(
                select(func.count())
                .select_from(LoginFlowRecord)
                .where(
                    LoginFlowRecord.source_digest == source_digest,
                    LoginFlowRecord.created_at >= since,
                )
            )
        ).one()

    async def add_login(self, flow: LoginFlow, source_digest: bytes) -> None:
        self.session.add(
            LoginFlowRecord(
                id=flow.id,
                state_digest=flow.state_digest,
                browser_digest=flow.browser_digest,
                sealed_material=flow.sealed_material,
                source_digest=source_digest,
                return_to=flow.return_to,
                created_at=flow.created_at,
                expires_at=flow.expires_at,
            )
        )
        await self.session.flush()

    async def invalidate_browser_flows(self, browser_digest: bytes, at: datetime) -> None:
        await self.session.execute(
            update(LoginFlowRecord)
            .where(
                LoginFlowRecord.browser_digest == browser_digest,
                LoginFlowRecord.consumed_at.is_(None),
            )
            .values(consumed_at=at, sealed_material=None)
        )

    async def lock_login(self, state_digest: bytes) -> LoginFlow | None:
        record = (
            await self.session.scalars(
                select(LoginFlowRecord)
                .where(
                    LoginFlowRecord.state_digest == state_digest,
                )
                .with_for_update()
            )
        ).one_or_none()
        return _flow(record) if record is not None else None

    async def lock_login_id(self, flow_id: UUID) -> LoginFlow | None:
        record = await self.session.get(LoginFlowRecord, flow_id, with_for_update=True)
        return _flow(record) if record is not None else None

    async def consume_login(self, flow_id: UUID, at: datetime) -> None:
        await self.session.execute(
            update(LoginFlowRecord)
            .where(LoginFlowRecord.id == flow_id)
            .values(
                consumed_at=at,
                sealed_material=None,
            )
        )

    async def complete_login(self, flow_id: UUID, at: datetime) -> None:
        await self.session.execute(
            update(LoginFlowRecord).where(LoginFlowRecord.id == flow_id).values(completed_at=at)
        )

    async def _lock_google_scope(
        self,
        identities: tuple[ExternalIdentityRecord, ...],
        previous_digest: bytes | None,
    ) -> dict[UUID, AccountRecord]:
        account_ids = {identity.account_id for identity in identities}
        if previous_digest is not None:
            previous = await self.session.scalar(
                select(SessionRecord.account_id).where(
                    SessionRecord.secret_digest == previous_digest
                )
            )
            if previous is not None:
                account_ids.add(previous)
        # Include retained same-person accounts: a concurrent ban/deletion must
        # settle before deciding whether a genuinely new actor may be created.
        locked = await self.session.scalars(
            select(AccountRecord)
            .where(AccountRecord.id.in_(account_ids))
            .order_by(AccountRecord.id)
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        )
        return {account.id: account for account in locked}

    async def resolve_google(
        self, identity: GoogleIdentity, at: datetime, previous_digest: bytes | None = None
    ) -> GoogleAccount:
        # Equal trusted subjects serialize across every retained incarnation.
        # Partial unique active-claim index remains the final database defence.
        await self.session.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(identity.subject, 0)))
        )
        identities = tuple(
            await self.session.scalars(
                select(ExternalIdentityRecord)
                .where(
                    ExternalIdentityRecord.issuer == identity.issuer,
                    ExternalIdentityRecord.subject == identity.subject,
                )
                .execution_options(populate_existing=True)
            )
        )
        accounts = await self._lock_google_scope(identities, previous_digest)
        active = tuple(row for row in identities if row.retired_at is None)
        if len(active) > 1:
            raise RuntimeError("Google identity has multiple active claims")
        if active:
            account = accounts[active[0].account_id]
            if account.deleted_at is None:
                # Session guards still apply current and retained-lineage bans;
                # existing banned actors retain their restricted support login.
                return GoogleAccount(account.id, None)
        for row in identities:
            prior = accounts[row.account_id]
            if prior.banned_at is not None or await identity_lineage_banned(self.session, prior.id):
                # Deletion and later credential changes cannot clear a known ban.
                return GoogleAccount(prior.id, prior.deleted_at)
        for row in identities:
            if accounts[row.account_id].deleted_at is None:
                raise RuntimeError("A live Google association was retired without deletion")
            if row.retired_at is None:
                await retire_deleted_claims(self.session, row.account_id)
        created_at = max(at, await self.now())
        account_id = uuid4()
        self.session.add(AccountRecord(id=account_id, created_at=created_at))
        await self.session.flush()
        self.session.add(
            ExternalIdentityRecord(
                id=uuid4(),
                account_id=account_id,
                issuer=identity.issuer,
                subject=identity.subject,
                created_at=created_at,
            )
        )
        await self.session.flush()
        return GoogleAccount(account_id, None)

    async def add_session(self, session: Session, digest: bytes) -> None:
        self.session.add(
            SessionRecord(
                id=session.id,
                account_id=session.account_id,
                secret_digest=digest,
                issued_at=session.issued_at,
                expires_at=session.expires_at,
                revoked_at=session.revoked_at,
            )
        )
        await self.session.flush()
        await record_foreground_activity(self.session, session.account_id, session.issued_at)


@dataclass(frozen=True, slots=True)
class SqlLoginUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[LoginTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlLoginTransaction(session)
