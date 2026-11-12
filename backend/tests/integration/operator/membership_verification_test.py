"""Real58 source/claim/receipt constraints and races; no staging/provider/mail calls."""

import asyncio
from dataclasses import dataclass

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.operator.membership_verification import (
    ManuallyVerifyMembership,
    ManuallyVerifyMembershipCommand,
    ManualMembershipClaimConflictError,
    ReadManualMembershipContext,
)
from studymate.domain.identity import StudentEmail
from studymate.domain.operator.membership_verification import ManualMembershipVerification
from studymate.infrastructure.operator.membership_verification_models import (
    OperatorMembershipIntentRecord,
    OperatorMembershipVerificationRecord,
)
from studymate.infrastructure.operator.membership_verification_transactions import (
    SqlManualMembershipUnitOfWork,
)
from studymate.infrastructure.persistence.email_models import (
    EmailChallengeRecord,
    EmailDeliveryRecord,
)
from studymate.infrastructure.persistence.identity_claims import retire_deleted_claims
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
    InstitutionalBindingRecord,
)
from studymate.infrastructure.persistence.onboarding_models import ProfileActivationRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import (
    record_manual_membership_event as record_manual,
)
from studymate.infrastructure.persistence.product_events import record_operator_audit
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.operator.test_reads import operator
from tests.integration.student_actor import Actor
from tests.integration.test_email_verification import services, start_command
from tests.integration.test_manual_stage_verification import owner

pytestmark = pytest.mark.integration
HASHER = Sha256SessionHasher()
FINGERPRINTER = HmacIntentFingerprinter(b"k" * 32)


@dataclass(frozen=True, slots=True)
class ManualCase:
    operator: Actor
    target: Actor
    command: ManuallyVerifyMembershipCommand
    sessions: async_sessionmaker[AsyncSession]

    def uow(self) -> SqlManualMembershipUnitOfWork:
        return SqlManualMembershipUnitOfWork(self.sessions, record_operator_audit, record_manual)

    def verify(self) -> ManuallyVerifyMembership:
        return ManuallyVerifyMembership(self.uow(), HASHER, FINGERPRINTER)


async def prepared(
    engine: AsyncEngine, email: str = "manual-operator@mail.apu.edu.my"
) -> ManualCase:
    viewer, target = await operator(engine), await owner(engine)
    start, _ = services(engine)
    challenge = await start(start_command(target.credential, StudentEmail(email)))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        identity = await session.scalar(
            select(ExternalIdentityRecord.id).where(ExternalIdentityRecord.account_id == target.id)
        )
        assert identity is not None
    return ManualCase(
        viewer,
        target,
        ManuallyVerifyMembershipCommand(
            viewer.credential,
            target.id,
            identity,
            challenge.id,
            StudentEmail(email),
            IntentKey("manual_verification_key"),
        ),
        sessions,
    )


async def test_actual_manual_source_exact_replay_and_retention_after_soft_delete(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    result = await api.verify()(api.command)
    assert await api.verify()(api.command) == result
    async with api.sessions() as session:
        proof = (await session.scalars(select(OperatorMembershipVerificationRecord))).one()
        assert proof.operator_id == api.operator.id
        assert proof.actor_session_id == result.actor_session_id
        assert proof.challenge_id == api.command.expected_challenge_id
        assert proof.google_identity_id == api.command.expected_google_identity_id
        assert proof.event_id == result.event_id
        assert (
            await session.scalars(select(OperatorMembershipIntentRecord))
        ).one().verification_id == result.id
        event = await session.get(ProductEventRecord, result.event_id)
        assert event is not None
        assert event.occurrence_key == result.occurrence_key
        challenge = await session.get(EmailChallengeRecord, result.challenge_id)
        assert challenge is not None
        assert challenge.consumed_at is None
        assert challenge.superseded_at == result.verified_at
        assert challenge.code_digest is None
        delivery = (
            await session.scalars(
                select(EmailDeliveryRecord).where(
                    EmailDeliveryRecord.challenge_id == result.challenge_id
                )
            )
        ).one()
        assert delivery.status == "cancelled"
        assert delivery.sealed_envelope is None
        assert await session.get(ProfileActivationRecord, api.target.id) is None
    async with api.sessions.begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == api.target.id)
            .values(deleted_at=func.clock_timestamp())
        )
        await retire_deleted_claims(session, api.target.id)
    context = await ReadManualMembershipContext(api.uow(), HASHER)(
        api.operator.credential, api.target.id
    )
    assert context is not None
    assert context.deleted
    assert context.manual_source == result


async def test_two_operators_cannot_claim_same_active_address_for_different_targets(
    identity_engine: AsyncEngine,
) -> None:
    first = await prepared(identity_engine)
    second = await prepared(identity_engine)
    outcomes = await asyncio.gather(
        first.verify()(first.command), second.verify()(second.command), return_exceptions=True
    )
    assert sum(isinstance(result, ManualMembershipVerification) for result in outcomes) == 1
    assert sum(isinstance(result, ManualMembershipClaimConflictError) for result in outcomes) == 1
    async with first.sessions() as session:
        assert len(tuple(await session.scalars(select(OperatorMembershipVerificationRecord)))) == 1
        assert len(tuple(await session.scalars(select(InstitutionalBindingRecord)))) == 1


async def test_concurrent_exact_key_replay_creates_one_proof_and_canonical_event(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    first, second = await asyncio.gather(api.verify()(api.command), api.verify()(api.command))
    assert first == second
    async with api.sessions() as session:
        assert len(tuple(await session.scalars(select(OperatorMembershipVerificationRecord)))) == 1
        assert (
            len(
                tuple(
                    await session.scalars(
                        select(ProductEventRecord).where(
                            ProductEventRecord.kind == "auth.email_confirmed"
                        )
                    )
                )
            )
            == 1
        )


async def fail_event(session: AsyncSession, source: ManualMembershipVerification) -> None:
    await record_manual(session, source)
    raise RuntimeError("synthetic canonical failure")


async def test_canonical_failure_rolls_back_binding_proof_outbox_and_challenge_terminal_state(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    usecase = ManuallyVerifyMembership(
        SqlManualMembershipUnitOfWork(api.sessions, record_operator_audit, fail_event),
        HASHER,
        FINGERPRINTER,
    )
    with pytest.raises(RuntimeError, match="synthetic canonical failure"):
        await usecase(api.command)
    async with api.sessions() as session:
        assert await session.get(InstitutionalBindingRecord, api.target.id) is None
        assert tuple(await session.scalars(select(OperatorMembershipVerificationRecord))) == ()
        assert tuple(await session.scalars(select(OperatorMembershipIntentRecord))) == ()
        challenge = await session.get(EmailChallengeRecord, api.command.expected_challenge_id)
        assert challenge is not None
        assert challenge.consumed_at is None
        assert challenge.superseded_at is None
        assert challenge.code_digest is not None
