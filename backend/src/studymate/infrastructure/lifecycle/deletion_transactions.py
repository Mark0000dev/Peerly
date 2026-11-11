"""Self-deletion persistence separates original receipt proof from fresh mutation authority."""

import hmac
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import IdentitySnapshot
from studymate.application.lifecycle.deletion_ports import DeletionWorkflowAuthorization
from studymate.application.lifecycle.intents import LifecycleIntent
from studymate.domain.lifecycle.states import (
    AccountLifecycle,
    DeletionTransition,
    LifecycleOperation,
)
from studymate.infrastructure.lifecycle.callbacks import LifecycleEffects, WorkflowAuthorizer
from studymate.infrastructure.lifecycle.storage import (
    apply_transition,
    read_intent,
    read_state,
    remember_intent,
)
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.transactions import open_transaction


@dataclass(slots=True)
class DeletionAuthority:
    original: IdentitySnapshot | None = None
    actor_id: UUID | None = None
    workflow: DeletionWorkflowAuthorization | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class SqlDeletionTransaction(SqlIdentityTransaction):
    session_digest: bytes = field(repr=False)
    workflow_id: UUID
    effects: LifecycleEffects
    workflow_authorizer: WorkflowAuthorizer
    authority: DeletionAuthority = field(default_factory=DeletionAuthority)

    async def lock_identity(self, secret_digest: bytes) -> IdentitySnapshot | None:
        if not hmac.compare_digest(secret_digest, self.session_digest):
            raise RuntimeError("Deletion credential differs from its transaction scope")
        identity = await SqlIdentityTransaction.lock_identity(self, secret_digest)
        if self.authority.original is None:
            self.authority.original = identity
        return identity

    def authenticated(self, account_id: UUID) -> None:
        identity = self.authority.original
        if identity is None or identity.session.account_id != account_id:
            raise RuntimeError("Deletion mutation differs from its actual original account")
        SqlIdentityTransaction.authenticated(self, account_id)
        self.authority.actor_id = account_id

    async def authorized_deletion_workflow(
        self,
        session_digest: bytes,
        workflow_id: UUID,
    ) -> DeletionWorkflowAuthorization | None:
        if workflow_id != self.workflow_id or not hmac.compare_digest(
            session_digest, self.session_digest
        ):
            raise RuntimeError("Deletion proof differs from its transaction scope")
        workflow = await self.workflow_authorizer(self.session, session_digest, workflow_id)
        identity = self.authority.original
        if workflow is not None and (
            identity is None
            or (workflow.id, workflow.account_id, workflow.session_id)
            != (self.workflow_id, identity.session.account_id, identity.session.id)
        ):
            raise RuntimeError("Deletion authorizer returned another actual workflow owner")
        self.authority.workflow = workflow
        return workflow

    def original_session(self) -> IdentitySnapshot:
        identity, workflow = self.authority.original, self.authority.workflow
        if identity is None or workflow is None:
            raise RuntimeError("Deletion lacks its actual original session/workflow proof")
        return identity

    async def target_lifecycle(self, account_id: UUID) -> AccountLifecycle | None:
        identity = self.original_session()
        if account_id != identity.session.account_id or self.authority.actor_id != account_id:
            raise RuntimeError("Deletion state read lacks fresh self mutation authority")
        return await read_state(self.session, account_id)

    async def prior_lifecycle_intent(
        self,
        actor_id: UUID,
        operation: LifecycleOperation,
        key: IntentKey,
    ) -> LifecycleIntent | None:
        if (
            actor_id != self.original_session().session.account_id
            or operation != LifecycleOperation.DELETE
        ):
            raise RuntimeError("Deletion receipt differs from its actual actor/operation")
        # Only this owned receipt query can precede fresh live-session authorization.
        return await read_intent(self.session, actor_id, operation, key)

    async def apply_deletion_transition(self, transition: DeletionTransition) -> None:
        identity = self.original_session()
        source = transition.revision
        if self.authority.actor_id != identity.session.account_id or (
            source.account_id,
            source.actor_session_id,
            source.workflow_id,
        ) != (identity.session.account_id, identity.session.id, self.workflow_id):
            raise RuntimeError("Deletion source lacks actual fresh self/workflow authority")
        await apply_transition(self.session, transition, self.effects)

    async def remember_lifecycle_intent(self, intent: LifecycleIntent, at: datetime) -> None:
        identity = self.original_session()
        if (
            intent.actor_id != self.authority.actor_id
            or not isinstance(intent.result, DeletionTransition)
            or (
                intent.result.revision.account_id,
                intent.result.revision.actor_session_id,
                intent.result.revision.workflow_id,
            )
            != (identity.session.account_id, identity.session.id, self.workflow_id)
        ):
            raise RuntimeError("Deletion intent differs from actual self/session/workflow source")
        await remember_intent(self.session, intent, identity.session.id, at)


@dataclass(frozen=True, slots=True)
class SqlDeletionUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    effects: LifecycleEffects
    workflow_authorizer: WorkflowAuthorizer

    @asynccontextmanager
    async def transaction(
        self,
        session_digest: bytes,
        workflow_id: UUID,
    ) -> AsyncIterator[SqlDeletionTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlDeletionTransaction(
                session,
                session_digest=session_digest,
                workflow_id=workflow_id,
                effects=self.effects,
                workflow_authorizer=self.workflow_authorizer,
            )
