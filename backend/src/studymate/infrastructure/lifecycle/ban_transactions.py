"""Actual role-guarded ban transactions with ordered account locks and required effects."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import IdentitySnapshot
from studymate.application.lifecycle.intents import LifecycleIntent
from studymate.domain.lifecycle.states import AccountLifecycle, BanTransition, LifecycleOperation
from studymate.infrastructure.lifecycle.callbacks import LifecycleEffects
from studymate.infrastructure.lifecycle.storage import (
    apply_transition,
    read_intent,
    read_state,
    remember_intent,
)
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.transactions import open_transaction


@dataclass(slots=True)
class BanIdentity:
    original: IdentitySnapshot | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class SqlBanTransaction(SqlOperatorTransaction):
    target_account_id: UUID
    effects: LifecycleEffects
    identity: BanIdentity = field(default_factory=BanIdentity)

    async def lock_identity(self, secret_digest: bytes) -> IdentitySnapshot | None:
        original = await self.lock_identity_for_peer(secret_digest, self.target_account_id)
        self.identity.original = original
        return original

    def actor_session(self) -> IdentitySnapshot:
        access = self.checked_access()
        identity = self.identity.original
        if identity is None or identity.session.account_id != access.account_id:
            raise RuntimeError("Ban transaction lacks its actual authenticated session")
        return identity

    async def target_lifecycle(self, account_id: UUID) -> AccountLifecycle | None:
        self.actor_session()
        if account_id != self.target_account_id:
            raise RuntimeError("Lifecycle target differs from ordered lock scope")
        return await read_state(self.session, account_id)

    async def prior_lifecycle_intent(
        self,
        actor_id: UUID,
        operation: LifecycleOperation,
        key: IntentKey,
    ) -> LifecycleIntent | None:
        if (
            actor_id != self.actor_session().session.account_id
            or operation == LifecycleOperation.DELETE
        ):
            raise RuntimeError("Ban receipt scope differs from its actual actor/operation")
        return await read_intent(self.session, actor_id, operation, key)

    async def apply_ban_transition(self, transition: BanTransition) -> None:
        identity = self.actor_session()
        source = transition.revision
        if source is None or (
            source.account_id,
            source.actor_session_id,
            source.operator_access,
        ) != (self.target_account_id, identity.session.id, self.checked_access()):
            raise RuntimeError("Ban source differs from actual target/session/operator authority")
        await apply_transition(self.session, transition, self.effects)

    async def remember_lifecycle_intent(self, intent: LifecycleIntent, at: datetime) -> None:
        identity = self.actor_session()
        if (
            intent.actor_id != identity.session.account_id
            or not isinstance(intent.result, BanTransition)
            or intent.result.after.account_id != self.target_account_id
        ):
            raise RuntimeError("Ban intent differs from actual actor/target/result scope")
        await remember_intent(self.session, intent, identity.session.id, at)


@dataclass(frozen=True, slots=True)
class SqlBanUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    effects: LifecycleEffects
    operator_audit_recorder: OperatorAuditRecorder

    @asynccontextmanager
    async def transaction(
        self,
        actor_secret_digest: bytes,
        target_account_id: UUID,
    ) -> AsyncIterator[SqlBanTransaction]:
        async with open_transaction(self.sessions) as session:
            # Prelock establishes only sorted lock scope. The use case still invokes
            # the shared live-session and actual-current-role guard before any read.
            await SqlIdentityTransaction(session).lock_identity_for_peer(
                actor_secret_digest, target_account_id
            )
            yield SqlBanTransaction(
                session,
                self.operator_audit_recorder,
                target_account_id=target_account_id,
                effects=self.effects,
            )
