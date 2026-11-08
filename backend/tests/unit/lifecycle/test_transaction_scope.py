"""Scope rejection must occur before database access or mutation authority is recorded."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.application.lifecycle.deletion_ports import DeletionWorkflowAuthorization
from studymate.application.lifecycle.intents import LifecycleResult
from studymate.infrastructure.lifecycle.deletion_transactions import SqlDeletionTransaction


async def forbidden_effect(session: AsyncSession, transition: LifecycleResult) -> None:
    del session, transition
    raise AssertionError("Rejected scope must never invoke effects")


async def forbidden_authorizer(
    session: AsyncSession, session_digest: bytes, workflow_id: UUID
) -> DeletionWorkflowAuthorization | None:
    del session, session_digest, workflow_id
    raise AssertionError("Rejected scope must never inspect proof")


async def test_unbound_deletion_transaction_rejects_foreign_credential_and_actor() -> None:
    # No engine: any attempted SQL would fail. These guards precede I/O.
    async with AsyncSession() as session:
        tx = SqlDeletionTransaction(
            session,
            session_digest=b"original",
            workflow_id=uuid4(),
            effects=forbidden_effect,
            workflow_authorizer=forbidden_authorizer,
        )
        with pytest.raises(RuntimeError, match="credential"):
            await tx.lock_identity(b"different")
        with pytest.raises(RuntimeError, match="original account"):
            tx.authenticated(uuid4())
        assert tx.authority.actor_id is None
