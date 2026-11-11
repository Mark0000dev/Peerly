"""Actual account/session workflow locks and narrow, separate status-proof reads."""

import hmac
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.identity.sessions import IdentitySnapshot
from studymate.application.lifecycle.deletion_ports import DeletionWorkflowAuthorization
from studymate.application.lifecycle.recovery import DeletionWorkflow
from studymate.domain.lifecycle.states import DeletionRevision
from studymate.domain.membership import GOOGLE_ISSUER
from studymate.infrastructure.lifecycle.models import LifecycleRevisionRecord
from studymate.infrastructure.lifecycle.workflow_models import AccountDeletionWorkflowRecord
from studymate.infrastructure.persistence.identity_models import (
    ExternalIdentityRecord,
    SessionRecord,
)
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.transactions import open_transaction


def workflow_value(row: AccountDeletionWorkflowRecord) -> DeletionWorkflow:
    return DeletionWorkflow(
        DeletionWorkflowAuthorization(row.id, row.account_id, row.session_id, row.expires_at),
        row.generation,
        row.created_at,
    )


@dataclass(slots=True)
class _PreparationAuthority:
    identity: IdentitySnapshot | None = None
    authenticated: bool = False


@dataclass(frozen=True, slots=True)
class SqlDeletionPreparationTransaction(SqlIdentityTransaction):
    session_digest: bytes = field(repr=False)
    authority: _PreparationAuthority = field(default_factory=_PreparationAuthority)

    async def lock_identity(self, secret_digest: bytes) -> IdentitySnapshot | None:
        if not hmac.compare_digest(secret_digest, self.session_digest):
            raise RuntimeError("Deletion preparation credential changed within its locked scope")
        identity = await SqlIdentityTransaction.lock_identity(self, secret_digest)
        if identity is not None:
            google = await self.session.scalar(
                select(ExternalIdentityRecord.account_id).where(
                    ExternalIdentityRecord.account_id == identity.session.account_id,
                    ExternalIdentityRecord.issuer == GOOGLE_ISSUER,
                )
            )
            if google is None:
                return None
        self.authority.identity = identity
        return identity

    def authenticated(self, account_id: UUID) -> None:
        identity = self.authority.identity
        if identity is None or account_id != identity.session.account_id:
            raise RuntimeError("Deletion preparation lacks its actual authenticated session")
        SqlIdentityTransaction.authenticated(self, account_id)
        self.authority.authenticated = True

    def _identity(self, account_id: UUID, session_id: UUID) -> IdentitySnapshot:
        identity = self.authority.identity
        if (
            identity is None
            or not self.authority.authenticated
            or (account_id, session_id) != (identity.session.account_id, identity.session.id)
        ):
            raise RuntimeError("Deletion workflow differs from the authenticated owner/session")
        return identity

    async def latest_workflow(self, account_id: UUID, session_id: UUID) -> DeletionWorkflow | None:
        self._identity(account_id, session_id)
        row = await self.session.scalar(
            select(AccountDeletionWorkflowRecord)
            .where(
                AccountDeletionWorkflowRecord.account_id == account_id,
                AccountDeletionWorkflowRecord.session_id == session_id,
            )
            .order_by(AccountDeletionWorkflowRecord.generation.desc())
            .limit(1)
            .with_for_update()
        )
        return workflow_value(row) if row is not None else None

    async def create_workflow(self, workflow: DeletionWorkflow, status_digest: bytes) -> None:
        source = workflow.authorization
        identity = self._identity(source.account_id, source.session_id)
        prior = await self.latest_workflow(source.account_id, source.session_id)
        if workflow.generation != (prior.generation + 1 if prior is not None else 1):
            raise RuntimeError("Deletion workflow lost its actual monotonic generation")
        if source.expires_at > identity.session.expires_at:
            raise RuntimeError("Deletion workflow cannot outlive its original session")
        self.session.add(
            AccountDeletionWorkflowRecord(
                id=source.id,
                account_id=source.account_id,
                session_id=source.session_id,
                generation=workflow.generation,
                created_at=workflow.created_at,
                expires_at=source.expires_at,
                status_secret_digest=status_digest,
            )
        )
        await self.session.flush()


@dataclass(frozen=True, slots=True)
class SqlPrepareDeletionUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(
        self, session_digest: bytes
    ) -> AsyncIterator[SqlDeletionPreparationTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlDeletionPreparationTransaction(session, session_digest)


@dataclass(slots=True)
class _StatusAuthority:
    workflow: DeletionWorkflow | None = None


@dataclass(frozen=True, slots=True)
class SqlDeletionStatusTransaction:
    session: AsyncSession
    status_digest: bytes = field(repr=False)
    authority: _StatusAuthority = field(default_factory=_StatusAuthority)

    async def now(self) -> datetime:
        return await SqlIdentityTransaction(self.session).now()

    async def workflow_for_status(self, status_digest: bytes) -> DeletionWorkflow | None:
        if not hmac.compare_digest(status_digest, self.status_digest):
            raise RuntimeError("Deletion status credential changed within its narrow proof scope")
        row = await self.session.scalar(
            select(AccountDeletionWorkflowRecord)
            .where(AccountDeletionWorkflowRecord.status_secret_digest == status_digest)
            .with_for_update()
        )
        self.authority.workflow = workflow_value(row) if row is not None else None
        return self.authority.workflow

    async def committed_deletion(self, workflow_id: UUID) -> DeletionRevision | None:
        workflow = self.authority.workflow
        if workflow is None or workflow.authorization.id != workflow_id:
            raise RuntimeError("Deletion status has no actual owned workflow proof")
        row = (
            await self.session.scalars(
                select(LifecycleRevisionRecord).where(
                    LifecycleRevisionRecord.workflow_id == workflow_id,
                    LifecycleRevisionRecord.operation == "delete",
                )
            )
        ).one_or_none()
        if row is None:
            return None
        return DeletionRevision(
            row.id, row.account_id, row.version, row.changed_at, row.actor_session_id, workflow_id
        )


@dataclass(frozen=True, slots=True)
class SqlDeletionStatusUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(
        self, status_digest: bytes
    ) -> AsyncIterator[SqlDeletionStatusTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlDeletionStatusTransaction(session, status_digest)


async def authorize_deletion_workflow(
    session: AsyncSession, session_digest: bytes, workflow_id: UUID
) -> DeletionWorkflowAuthorization | None:
    """Caller already holds actual actor account/session locks; no public-ID authority."""
    row = (
        await session.execute(
            select(AccountDeletionWorkflowRecord, SessionRecord.expires_at)
            .join(
                SessionRecord,
                (SessionRecord.id == AccountDeletionWorkflowRecord.session_id)
                & (SessionRecord.account_id == AccountDeletionWorkflowRecord.account_id),
            )
            .where(
                SessionRecord.secret_digest == session_digest,
                AccountDeletionWorkflowRecord.id == workflow_id,
            )
            .with_for_update(of=AccountDeletionWorkflowRecord)
        )
    ).one_or_none()
    if row is None:
        return None
    source, session_expiry = row
    now = await SqlIdentityTransaction(session).now()
    if source.expires_at > session_expiry or now >= min(source.expires_at, session_expiry):
        return None
    return workflow_value(source).authorization
