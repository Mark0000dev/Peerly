"""Required composition hooks; actual shared effects and proof policy stay main-owned."""

from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from studymate.application.lifecycle.deletion_ports import DeletionWorkflowAuthorization
from studymate.application.lifecycle.intents import LifecycleResult


class LifecycleEffects(Protocol):
    async def __call__(self, session: AsyncSession, transition: LifecycleResult) -> None:
        """Apply actual shared effects after source flush, within the caller transaction.

        No commit, network, or replay/no-op invocation. A failure rolls back flags,
        source, effects and intent together. Composition must supply a real adapter;
        there is deliberately no default callback.
        """
        ...


class WorkflowAuthorizer(Protocol):
    async def __call__(
        self, session: AsyncSession, session_digest: bytes, workflow_id: UUID
    ) -> DeletionWorkflowAuthorization | None:
        """Validate original credential and actual owned workflow under held locks.

        Resolution alone never grants a fresh mutation to a revoked session. The
        application separately restricts it to an original committed receipt.
        """
        ...
