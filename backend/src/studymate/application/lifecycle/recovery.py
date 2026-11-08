"""Stable deletion preparation and narrowly authenticated outcome recovery.

A pending status is not proof that a delayed deletion cannot commit. The status
credential never authorizes deletion, account reads or a new application session.
"""

import re
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from studymate.application.identity.sessions import (
    IdentityTransaction,
    SessionCredential,
    SessionHasher,
    UnauthenticatedError,
    require_session_identity,
)
from studymate.application.lifecycle.deletion_ports import DeletionWorkflowAuthorization
from studymate.domain.lifecycle.states import DeletionRevision
from studymate.domain.time import require_aware

WORKFLOW_LIFETIME = timedelta(minutes=20)


class DeletionStatusUnavailableError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class DeletionStatusCredential:
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if re.fullmatch(r"[A-Za-z0-9_-]{43}", self.value) is None:
            raise ValueError("Deletion status requires its opaque narrow credential")


@dataclass(frozen=True, slots=True)
class DeletionWorkflow:
    authorization: DeletionWorkflowAuthorization
    generation: int
    created_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.created_at)
        if isinstance(self.generation, bool) or self.generation < 1:
            raise ValueError("Deletion workflow requires its actual session generation")
        if self.created_at >= self.authorization.expires_at:
            raise ValueError("Deletion workflow expiry must follow its creation")


@dataclass(frozen=True, slots=True)
class PreparedDeletionWorkflow:
    authorization: DeletionWorkflowAuthorization
    status_credential: DeletionStatusCredential = field(repr=False)


@dataclass(frozen=True, slots=True)
class DeletionStatus:
    authorization: DeletionWorkflowAuthorization
    deletion: DeletionRevision | None


class DeletionStatusProofs(Protocol):
    def issue(
        self, authorization: DeletionWorkflowAuthorization, session_digest: bytes
    ) -> DeletionStatusCredential: ...

    def digest(self, credential: DeletionStatusCredential) -> bytes: ...


class PrepareDeletionTransaction(IdentityTransaction, Protocol):
    async def latest_workflow(
        self, account_id: UUID, session_id: UUID
    ) -> DeletionWorkflow | None: ...

    async def create_workflow(self, workflow: DeletionWorkflow, status_digest: bytes) -> None: ...


class PrepareDeletionUnitOfWork(Protocol):
    def transaction(
        self, session_digest: bytes
    ) -> AbstractAsyncContextManager[PrepareDeletionTransaction]: ...


class DeletionStatusTransaction(Protocol):
    async def now(self) -> datetime: ...

    async def workflow_for_status(self, status_digest: bytes) -> DeletionWorkflow | None: ...

    async def committed_deletion(self, workflow_id: UUID) -> DeletionRevision | None: ...


class DeletionStatusUnitOfWork(Protocol):
    def transaction(
        self, status_digest: bytes
    ) -> AbstractAsyncContextManager[DeletionStatusTransaction]: ...


def _alive(workflow: DeletionWorkflowAuthorization, at: datetime) -> None:
    if at >= workflow.expires_at:
        raise DeletionStatusUnavailableError


@dataclass(frozen=True, slots=True)
class PrepareOwnDeletion:
    unit_of_work: PrepareDeletionUnitOfWork
    hasher: SessionHasher
    proofs: DeletionStatusProofs

    async def __call__(self, credential: SessionCredential) -> PreparedDeletionWorkflow:
        digest = await self.hasher.digest(credential)
        async with self.unit_of_work.transaction(digest) as transaction:
            identity, now = await require_session_identity(transaction, digest)
            owner = identity.session.account_id
            session_id = identity.session.id
            latest = await transaction.latest_workflow(owner, session_id)
            if latest is not None and (
                latest.authorization.account_id != owner
                or latest.authorization.session_id != session_id
            ):
                raise RuntimeError("Deletion preparation lost its actual session-owned source")
            if latest is not None and latest.authorization.expires_at > now:
                workflow = latest
                if workflow.authorization.expires_at > identity.session.expires_at:
                    raise RuntimeError("Deletion preparation outlives its original session")
            else:
                authorization = DeletionWorkflowAuthorization(
                    uuid4(),
                    owner,
                    session_id,
                    min(now + WORKFLOW_LIFETIME, identity.session.expires_at),
                )
                workflow = DeletionWorkflow(
                    authorization, latest.generation + 1 if latest is not None else 1, now
                )
                secret = self.proofs.issue(workflow.authorization, digest)
                await transaction.create_workflow(workflow, self.proofs.digest(secret))
            secret = self.proofs.issue(workflow.authorization, digest)
            final_now = await transaction.now()
            if not identity.session.is_active(final_now):
                raise UnauthenticatedError
            _alive(workflow.authorization, final_now)
            return PreparedDeletionWorkflow(workflow.authorization, secret)


@dataclass(frozen=True, slots=True)
class ReadOwnDeletionStatus:
    unit_of_work: DeletionStatusUnitOfWork
    proofs: DeletionStatusProofs

    async def __call__(self, credential: DeletionStatusCredential) -> DeletionStatus:
        digest = self.proofs.digest(credential)
        async with self.unit_of_work.transaction(digest) as transaction:
            workflow = await transaction.workflow_for_status(digest)
            if workflow is None:
                raise DeletionStatusUnavailableError
            authorization = workflow.authorization
            _alive(authorization, await transaction.now())
            deletion = await transaction.committed_deletion(authorization.id)
            if deletion is not None and (
                deletion.workflow_id != authorization.id
                or deletion.account_id != authorization.account_id
                or deletion.actor_session_id != authorization.session_id
            ):
                raise RuntimeError("Deletion status lost its actual owned committed source")
            _alive(authorization, await transaction.now())
            return DeletionStatus(authorization, deletion)
