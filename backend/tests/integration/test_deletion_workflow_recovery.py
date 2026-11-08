import asyncio
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.lifecycle.recovery import (
    DeletionStatusCredential,
    DeletionStatusUnavailableError,
    PrepareOwnDeletion,
    ReadOwnDeletionStatus,
)
from studymate.domain.membership import GOOGLE_ISSUER
from studymate.infrastructure.lifecycle.status_proofs import HmacDeletionStatusProofs
from studymate.infrastructure.lifecycle.workflow_models import AccountDeletionWorkflowRecord
from studymate.infrastructure.lifecycle.workflows import (
    SqlDeletionStatusUnitOfWork,
    SqlPrepareDeletionUnitOfWork,
    authorize_deletion_workflow,
)
from studymate.infrastructure.persistence.identity_models import (
    ExternalIdentityRecord,
    SessionRecord,
)
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.student_actor import Actor, actor

pytestmark = pytest.mark.integration
PROOFS = HmacDeletionStatusProofs(b"s" * 32)
HASHER = Sha256SessionHasher()


async def google_actor(engine: AsyncEngine) -> Actor:
    owner = await actor(engine, verified=False)
    async with async_sessionmaker(engine).begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        session.add(
            ExternalIdentityRecord(
                id=uuid4(),
                account_id=owner.id,
                issuer=GOOGLE_ISSUER,
                subject=f"synthetic-deletion-{owner.id}",
                created_at=now,
            )
        )
    return owner


async def test_real_concurrent_preflight_and_lost_response_reuse_one_workflow_and_secret(
    identity_engine: AsyncEngine,
) -> None:
    owner = await google_actor(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    prepare = PrepareOwnDeletion(SqlPrepareDeletionUnitOfWork(sessions), HASHER, PROOFS)
    first, second = await asyncio.gather(prepare(owner.credential), prepare(owner.credential))
    assert first == second
    assert await prepare(owner.credential) == first
    async with sessions() as session:
        records = tuple(await session.scalars(select(AccountDeletionWorkflowRecord)))
        assert len(records) == 1
        assert records[0].generation == 1
        assert records[0].account_id == owner.id
        assert records[0].status_secret_digest == PROOFS.digest(first.status_credential)
    read = ReadOwnDeletionStatus(SqlDeletionStatusUnitOfWork(sessions), PROOFS)
    pending = await read(first.status_credential)
    assert pending.deletion is None
    assert pending.authorization == first.authorization
    with pytest.raises(DeletionStatusUnavailableError):
        await read(DeletionStatusCredential("z" * 43))


async def test_workflow_command_authorization_requires_its_exact_original_session_digest(
    identity_engine: AsyncEngine,
) -> None:
    owner, other = await google_actor(identity_engine), await google_actor(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    prepared = await PrepareOwnDeletion(SqlPrepareDeletionUnitOfWork(sessions), HASHER, PROOFS)(
        owner.credential
    )
    async with sessions.begin() as session:
        transaction = SqlIdentityTransaction(session)
        digest = await HASHER.digest(owner.credential)
        assert await transaction.lock_identity(digest) is not None
        assert (
            await authorize_deletion_workflow(session, digest, prepared.authorization.id)
            == prepared.authorization
        )
    async with sessions.begin() as session:
        transaction = SqlIdentityTransaction(session)
        other_digest = await HASHER.digest(other.credential)
        assert await transaction.lock_identity(other_digest) is not None
        assert (
            await authorize_deletion_workflow(session, other_digest, prepared.authorization.id)
            is None
        )


async def test_revoked_session_cannot_prepare_but_its_narrow_status_proof_survives(
    identity_engine: AsyncEngine,
) -> None:
    owner = await google_actor(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    prepare = PrepareOwnDeletion(SqlPrepareDeletionUnitOfWork(sessions), HASHER, PROOFS)
    prepared = await prepare(owner.credential)
    async with sessions.begin() as session:
        await session.execute(
            update(SessionRecord)
            .where(SessionRecord.account_id == owner.id)
            .values(revoked_at=func.clock_timestamp())
        )
    with pytest.raises(UnauthenticatedError):
        await prepare(owner.credential)
    status = await ReadOwnDeletionStatus(SqlDeletionStatusUnitOfWork(sessions), PROOFS)(
        prepared.status_credential
    )
    assert status.deletion is None
    async with sessions.begin() as session:
        digest = await HASHER.digest(owner.credential)
        assert await SqlIdentityTransaction(session).lock_identity(digest) is not None
        assert (
            await authorize_deletion_workflow(session, digest, prepared.authorization.id)
            == prepared.authorization
        )


async def test_non_google_synthetic_session_cannot_create_a_google_deletion_workflow(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine, verified=False)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    with pytest.raises(UnauthenticatedError):
        await PrepareOwnDeletion(SqlPrepareDeletionUnitOfWork(sessions), HASHER, PROOFS)(
            owner.credential
        )
    async with sessions() as session:
        assert (
            await session.scalar(select(func.count()).select_from(AccountDeletionWorkflowRecord))
            == 0
        )
