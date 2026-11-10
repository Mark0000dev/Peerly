import asyncio
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import SessionCredential
from studymate.application.support.cases import (
    SOURCE_LIMIT,
    CreateSupportCase,
    CreateSupportCommand,
    PrepareSupport,
    ReadSupportCase,
    SupportQuotaError,
    SupportUnavailableError,
)
from studymate.domain.support.cases import (
    SupportContent,
    SupportReceipt,
    SupportStatus,
    SupportTopic,
)
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.support.models import (
    SupportCaseRecord,
    SupportProofRecord,
    SupportRevisionRecord,
)
from studymate.infrastructure.support.persistence import SqlSupportUnitOfWork
from studymate.infrastructure.support.proofs import OpaqueSupportProofs
from tests.integration.operator.test_reads import operator

pytestmark = pytest.mark.integration


class Hasher:
    async def digest(self, credential: SessionCredential) -> bytes:
        raise AssertionError(
            f"Anonymous support must never look up a session: {type(credential).__name__}"
        )


async def business_only_event(
    session: AsyncSession, actor_id: UUID | None, receipt: SupportReceipt
) -> None:
    assert actor_id is None
    assert await session.get(SupportRevisionRecord, (receipt.case_id, receipt.version)) is not None


def services(engine: AsyncEngine) -> tuple[PrepareSupport, CreateSupportCase, ReadSupportCase]:
    uow = SqlSupportUnitOfWork(
        async_sessionmaker(engine, expire_on_commit=False), business_only_event
    )
    proofs = OpaqueSupportProofs()
    return (
        PrepareSupport(uow, proofs),
        CreateSupportCase(uow, proofs, Hasher(), HmacIntentFingerprinter(b"k" * 32)),
        ReadSupportCase(uow, proofs),
    )


async def test_anonymous_case_replay_is_immutable_but_owned_status_reads_actual_revision(
    identity_engine: AsyncEngine,
) -> None:
    prepare, create, read = services(identity_engine)
    proof, _ = await prepare(b"s" * 32)
    content = SupportContent(
        SupportTopic.DELETED_ACCOUNT,
        "reply@example.test",
        "Private sign-in difficulty",
        "Private optional details",
    )
    command = CreateSupportCommand(proof, content, IntentKey("support_001"))
    first, replay = await asyncio.gather(create(command), create(command))
    assert first == replay
    owner = await operator(identity_engine)
    async with async_sessionmaker(identity_engine).begin() as session:
        assert await session.scalar(select(func.count()).select_from(SupportCaseRecord)) == 1
        session.add(
            SupportRevisionRecord(
                case_id=first.case_id,
                version=2,
                status="in_review",
                changed_by_id=owner.id,
                operator_access_version=1,
                changed_at=first.changed_at + timedelta(seconds=1),
            )
        )
    assert (await read(proof, first.case_id)).status == SupportStatus.IN_REVIEW
    assert (await create(command)).status == SupportStatus.RECEIVED
    foreign, _ = await prepare(b"t" * 32)
    with pytest.raises(SupportUnavailableError):
        await read(foreign, first.case_id)
    with pytest.raises(SupportUnavailableError):
        await read(proof, uuid4())
    with pytest.raises(IdempotencyConflictError):
        await create(
            CreateSupportCommand(
                proof,
                SupportContent(SupportTopic.OTHER, "reply@example.test", "Different request"),
                command.intent_key,
            )
        )
    async with async_sessionmaker(identity_engine).begin() as session:
        await session.execute(
            update(SupportProofRecord)
            .where(SupportProofRecord.digest == OpaqueSupportProofs().digest(proof))
            .values(expires_at=first.received_at + timedelta(microseconds=1))
        )
    with pytest.raises(SupportUnavailableError):
        await read(proof, first.case_id)


async def test_rotating_proof_does_not_bypass_source_quota_and_replay_does_not_spend_it(
    identity_engine: AsyncEngine,
) -> None:
    prepare, create, _ = services(identity_engine)
    content = SupportContent(SupportTopic.CANNOT_SIGN_IN, "reply@example.test", "Cannot sign in")
    commands = []
    for index in range(5):
        proof, _ = await prepare(b"s" * 32)
        commands.append(CreateSupportCommand(proof, content, IntentKey(f"support_{index:03}")))
    results = await asyncio.gather(*(create(command) for command in commands))
    assert len({result.case_id for result in results}) == SOURCE_LIMIT
    proof, _ = await prepare(b"s" * 32)
    with pytest.raises(SupportQuotaError):
        await create(CreateSupportCommand(proof, content, IntentKey("support_006")))
    assert await create(commands[0]) == results[0]


class RejectedSourceError(Exception):
    pass


async def reject_source(
    session: AsyncSession, actor_id: UUID | None, receipt: SupportReceipt
) -> None:
    await business_only_event(session, actor_id, receipt)
    raise RejectedSourceError


async def test_case_and_replay_roll_back_when_atomic_source_recorder_fails(
    identity_engine: AsyncEngine,
) -> None:
    prepare, _, _ = services(identity_engine)
    proof, _ = await prepare(b"s" * 32)
    proofs = OpaqueSupportProofs()
    create = CreateSupportCase(
        SqlSupportUnitOfWork(
            async_sessionmaker(identity_engine, expire_on_commit=False), reject_source
        ),
        proofs,
        Hasher(),
        HmacIntentFingerprinter(b"k" * 32),
    )
    command = CreateSupportCommand(
        proof,
        SupportContent(SupportTopic.OTHER, "reply@example.test", "Private problem"),
        IntentKey("support_001"),
    )
    with pytest.raises(RejectedSourceError):
        await create(command)
    async with async_sessionmaker(identity_engine)() as session:
        assert await session.scalar(select(func.count()).select_from(SupportCaseRecord)) == 0
        assert await session.get(SupportProofRecord, proofs.digest(proof)) is not None
    _, working, _ = services(identity_engine)
    assert (await working(command)).status == SupportStatus.RECEIVED
