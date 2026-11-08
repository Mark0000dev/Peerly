"""Actual owned workflow proof plus atomic deletion receipts; effects remain controlled."""

from dataclasses import replace
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.lifecycle.commands import DeleteOwnAccountCommand
from studymate.application.lifecycle.deletion_ports import DeletionWorkflowUnavailableError
from studymate.application.lifecycle.deletions import DeleteOwnAccount
from studymate.application.lifecycle.intents import LifecycleResult
from studymate.infrastructure.lifecycle.deletion_transactions import SqlDeletionUnitOfWork
from studymate.infrastructure.lifecycle.models import LifecycleIntentRecord, LifecycleRevisionRecord
from studymate.infrastructure.lifecycle.workflow_models import AccountDeletionWorkflowRecord
from studymate.infrastructure.lifecycle.workflows import authorize_deletion_workflow
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.lifecycle.test_transactions import controlled_effect
from tests.integration.student_actor import Actor, actor

pytestmark = pytest.mark.integration


async def revoke_owned_session(session: AsyncSession, transition: LifecycleResult) -> None:
    await controlled_effect(session, transition)
    # Controlled invalidation demonstrates revoked-original replay; not the complete
    # actual main deletion-effects adapter or canonical event integration.
    await session.execute(
        update(SessionRecord)
        .where(SessionRecord.account_id == transition.after.account_id)
        .values(revoked_at=func.clock_timestamp())
    )


async def command_for(engine: AsyncEngine, owner: Actor) -> DeleteOwnAccountCommand:
    async with async_sessionmaker(engine).begin() as session:
        stored = (
            await session.scalars(select(SessionRecord).where(SessionRecord.account_id == owner.id))
        ).one()
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        workflow_id = uuid4()
        session.add(
            AccountDeletionWorkflowRecord(
                id=workflow_id,
                account_id=owner.id,
                session_id=stored.id,
                generation=1,
                created_at=now,
                expires_at=now + timedelta(minutes=5),
                status_secret_digest=uuid4().bytes + uuid4().bytes,
            )
        )
    return DeleteOwnAccountCommand(owner.credential, workflow_id, IntentKey("delete-intent"))


def usecase(engine: AsyncEngine) -> DeleteOwnAccount:
    return DeleteOwnAccount(
        SqlDeletionUnitOfWork(
            async_sessionmaker(engine, expire_on_commit=False),
            revoke_owned_session,
            authorize_deletion_workflow,
        ),
        Sha256SessionHasher(),
        HmacIntentFingerprinter(b"d" * 32),
    )


async def test_original_revoked_session_recovers_only_its_committed_receipt(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine, verified=False)
    command = await command_for(identity_engine, owner)
    first = await usecase(identity_engine)(command)
    assert await usecase(identity_engine)(command) == first
    with pytest.raises(UnauthenticatedError):
        await usecase(identity_engine)(replace(command, intent_key=IntentKey("fresh-after-delete")))
    stranger = await actor(identity_engine)
    with pytest.raises(DeletionWorkflowUnavailableError):
        await usecase(identity_engine)(replace(command, credential=stranger.credential))
    async with async_sessionmaker(identity_engine)() as session:
        account = await session.get(AccountRecord, owner.id)
        assert account is not None
        assert account.deleted_at == first.after.deleted_at
        assert account.lifecycle_version == 1
        assert await session.scalar(select(func.count()).select_from(LifecycleRevisionRecord)) == 1
        assert await session.scalar(select(func.count()).select_from(LifecycleIntentRecord)) == 1


async def test_expired_workflow_cannot_recover_committed_result(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    command = await command_for(identity_engine, owner)
    await usecase(identity_engine)(command)
    async with async_sessionmaker(identity_engine).begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        await session.execute(
            update(AccountDeletionWorkflowRecord)
            .where(AccountDeletionWorkflowRecord.id == command.workflow_id)
            .values(created_at=now - timedelta(minutes=2), expires_at=now - timedelta(minutes=1))
        )
    with pytest.raises(DeletionWorkflowUnavailableError):
        await usecase(identity_engine)(command)


async def test_deletion_adapter_rejects_authority_and_transaction_scope_confusion(
    identity_engine: AsyncEngine,
) -> None:
    from studymate.application.identity.sessions import require_session_identity
    from studymate.application.lifecycle.intents import LifecycleIntent
    from studymate.domain.lifecycle.states import (
        AccountLifecycle,
        BanTransition,
        LifecycleOperation,
        plan_deletion,
    )

    owner = await actor(identity_engine)
    command = await command_for(identity_engine, owner)
    hasher = Sha256SessionHasher()
    uow = usecase(identity_engine).unit_of_work
    digest = await hasher.digest(owner.credential)
    async with uow.transaction(digest, command.workflow_id) as tx:
        # Public port exposes proof and state guards; no raw ORM authority shortcuts.
        with pytest.raises(RuntimeError, match="proof"):
            await tx.prior_lifecycle_intent(owner.id, LifecycleOperation.DELETE, command.intent_key)
        identity = await tx.lock_identity(digest)
        assert identity is not None
        with pytest.raises(RuntimeError, match="scope"):
            await tx.authorized_deletion_workflow(digest, uuid4())
        authorization = await tx.authorized_deletion_workflow(digest, command.workflow_id)
        assert authorization is not None
        with pytest.raises(RuntimeError, match="mutation authority"):
            await tx.target_lifecycle(owner.id)
        with pytest.raises(RuntimeError, match="actor/operation"):
            await tx.prior_lifecycle_intent(owner.id, LifecycleOperation.BAN, command.intent_key)
        await require_session_identity(tx, digest)
        state = await tx.target_lifecycle(owner.id)
        assert state is not None
        wrong = plan_deletion(
            state,
            change_id=uuid4(),
            at=await tx.now(),
            actor_session_id=identity.session.id,
            workflow_id=uuid4(),
        )
        with pytest.raises(RuntimeError, match="authority"):
            await tx.apply_deletion_transition(wrong)
        noop = BanTransition(AccountLifecycle(owner.id), AccountLifecycle(owner.id), None)
        with pytest.raises(RuntimeError, match="self/session/workflow"):
            await tx.remember_lifecycle_intent(
                LifecycleIntent(
                    owner.id, LifecycleOperation.UNBAN, IntentKey("wrong-result"), b"x" * 32, noop
                ),
                await tx.now(),
            )
