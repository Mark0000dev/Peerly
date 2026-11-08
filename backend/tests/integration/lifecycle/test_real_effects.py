"""Actual main lifecycle effects with retained business history and atomic rollback."""

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.lifecycle.bans import ChangeAccountBan
from studymate.application.lifecycle.commands import ChangeAccountBanCommand
from studymate.application.lifecycle.deletions import DeleteOwnAccount
from studymate.application.lifecycle.intents import LifecycleResult
from studymate.domain.lifecycle.states import LifecycleReason
from studymate.infrastructure.lifecycle.ban_transactions import SqlBanUnitOfWork
from studymate.infrastructure.lifecycle.deletion_transactions import SqlDeletionUnitOfWork
from studymate.infrastructure.lifecycle.effects import apply_lifecycle_effects
from studymate.infrastructure.lifecycle.models import LifecycleIntentRecord, LifecycleRevisionRecord
from studymate.infrastructure.lifecycle.workflows import authorize_deletion_workflow
from studymate.infrastructure.persistence.email_models import (
    EmailChallengeRecord,
    EmailDeliveryRecord,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from studymate.infrastructure.requests.models import ConnectionRequestRecord, RequestSendDayRecord
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.lifecycle.test_deletion_transactions import command_for
from tests.integration.operator.test_reads import operator
from tests.integration.requests.fixture import prepared, sent
from tests.integration.student_actor import Actor, actor

pytestmark = pytest.mark.integration
ONE_SEND = 1


async def seed_verification(engine: AsyncEngine, owner: Actor) -> tuple[UUID, UUID]:
    async with async_sessionmaker(engine).begin() as session:
        stored = (
            await session.scalars(select(SessionRecord).where(SessionRecord.account_id == owner.id))
        ).one()
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        challenge_id, delivery_id = uuid4(), uuid4()
        session.add(
            EmailChallengeRecord(
                id=challenge_id,
                account_id=owner.id,
                session_id=stored.id,
                email=f"synthetic-{owner.id.hex}@mail.apu.edu.my",
                code_digest=b"c" * 32,
                source_digest=b"s" * 32,
                created_at=now,
                resend_at=now + timedelta(minutes=1),
                expires_at=now + timedelta(minutes=5),
                attempts=0,
            )
        )
        await session.flush()
        session.add(
            EmailDeliveryRecord(
                id=delivery_id,
                challenge_id=challenge_id,
                status="inflight",
                sealed_envelope=b"synthetic-sealed-envelope",
                created_at=now,
                due_at=now,
                attempts=1,
                lease_generation=1,
                lease_until=now + timedelta(minutes=1),
            )
        )
    return challenge_id, delivery_id


def deletion(engine: AsyncEngine) -> DeleteOwnAccount:
    return DeleteOwnAccount(
        SqlDeletionUnitOfWork(
            async_sessionmaker(engine, expire_on_commit=False),
            apply_lifecycle_effects,
            authorize_deletion_workflow,
        ),
        Sha256SessionHasher(),
        HmacIntentFingerprinter(b"r" * 32),
    )


async def test_real_delete_revokes_sessions_cancels_delivery_and_retains_originals(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine, verified=False)
    challenge_id, delivery_id = await seed_verification(identity_engine, owner)
    command = await command_for(identity_engine, owner)
    async with async_sessionmaker(identity_engine).begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        session.add(
            SessionRecord(
                id=uuid4(),
                account_id=owner.id,
                secret_digest=uuid4().bytes + uuid4().bytes,
                issued_at=now,
                expires_at=now + timedelta(days=1),
            )
        )
    result = await deletion(identity_engine)(command)
    assert await deletion(identity_engine)(command) == result
    async with async_sessionmaker(identity_engine)() as session:
        stored_sessions = tuple(
            await session.scalars(select(SessionRecord).where(SessionRecord.account_id == owner.id))
        )
        assert len(stored_sessions) == len(("original", "additional"))
        assert all(stored.revoked_at == result.after.deleted_at for stored in stored_sessions)
        challenge = await session.get(EmailChallengeRecord, challenge_id)
        delivery = await session.get(EmailDeliveryRecord, delivery_id)
        assert challenge is not None
        assert challenge.superseded_at == result.after.deleted_at
        assert challenge.code_digest is None
        assert challenge.email.endswith("@mail.apu.edu.my")
        assert delivery is not None
        assert delivery.status == "cancelled"
        assert delivery.sealed_envelope is None
        assert delivery.lease_until is None
        events = tuple(
            await session.scalars(
                select(ProductEventRecord).where(
                    ProductEventRecord.kind == "account.lifecycle_changed"
                )
            )
        )
        assert len(events) == 1
        assert events[0].account_id == owner.id
        assert events[0].lifecycle_account_id == owner.id
        assert events[0].lifecycle_revision_id == result.revision.id
        assert events[0].request_id is None
        assert await session.get(AccountRecord, owner.id) is not None


@pytest.mark.parametrize("cancelled", [False, True])
async def test_real_effects_roll_back_with_flags_sources_intents_and_canonical(
    identity_engine: AsyncEngine,
    cancelled: bool,
) -> None:
    owner = await actor(identity_engine, verified=False)
    challenge_id, delivery_id = await seed_verification(identity_engine, owner)
    command = await command_for(identity_engine, owner)

    async def interrupted_effects(session: AsyncSession, transition: LifecycleResult) -> None:
        await apply_lifecycle_effects(session, transition)
        if cancelled:
            raise asyncio.CancelledError
        raise RuntimeError("synthetic post-effects failure")

    fail = replace(
        deletion(identity_engine),
        unit_of_work=SqlDeletionUnitOfWork(
            async_sessionmaker(identity_engine, expire_on_commit=False),
            interrupted_effects,
            authorize_deletion_workflow,
        ),
    )
    expected = asyncio.CancelledError if cancelled else RuntimeError
    with pytest.raises(expected):
        await fail(command)
    async with async_sessionmaker(identity_engine)() as session:
        stored = (
            await session.scalars(select(SessionRecord).where(SessionRecord.account_id == owner.id))
        ).one()
        assert stored.revoked_at is None
        account = await session.get(AccountRecord, owner.id)
        assert account is not None
        assert account.deleted_at is None
        assert account.lifecycle_version is None
        challenge = await session.get(EmailChallengeRecord, challenge_id)
        delivery = await session.get(EmailDeliveryRecord, delivery_id)
        assert challenge is not None
        assert challenge.code_digest == b"c" * 32
        assert challenge.superseded_at is None
        assert delivery is not None
        assert delivery.status == "inflight"
        for table in (LifecycleRevisionRecord, LifecycleIntentRecord, ProductEventRecord):
            assert await session.scalar(select(func.count()).select_from(table)) == 0
    assert (await deletion(identity_engine)(command)).revision.account_id == owner.id


async def test_ban_closes_pending_request_without_refunding_or_revoking_and_unban_does_not_reopen(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    request = await sent(api, sender, recipient)
    owner = await operator(identity_engine)
    command = ChangeAccountBanCommand(
        owner.credential,
        sender.id,
        True,
        LifecycleReason("private moderation reason"),
        IntentKey("ban-pending"),
    )
    usecase = ChangeAccountBan(
        SqlBanUnitOfWork(api.sessions, apply_lifecycle_effects, record_operator_audit),
        Sha256SessionHasher(),
        HmacIntentFingerprinter(b"r" * 32),
    )
    first, replay = await asyncio.gather(usecase(command), usecase(command))
    assert first == replay
    async with api.sessions() as session:
        pending = await session.get(ConnectionRequestRecord, request.id)
        assert pending is not None
        assert pending.state == "unavailable"
        assert pending.current_version == request.version + 1
        budget = (
            await session.scalars(
                select(RequestSendDayRecord).where(RequestSendDayRecord.sender_id == sender.id)
            )
        ).one()
        assert budget.successful_count == ONE_SEND
        sessions = tuple(
            await session.scalars(
                select(SessionRecord).where(SessionRecord.account_id == sender.id)
            )
        )
        assert sessions
        assert all(stored.revoked_at is None for stored in sessions)
    await usecase(replace(command, banned=False, intent_key=IntentKey("unban-pending")))
    async with api.sessions() as session:
        retained = await session.get(ConnectionRequestRecord, request.id)
        assert retained is not None
        assert retained.state == "unavailable"
        lifecycle_events = tuple(
            await session.scalars(
                select(ProductEventRecord).where(
                    ProductEventRecord.kind == "account.lifecycle_changed"
                )
            )
        )
        assert len(lifecycle_events) == len(("ban", "unban"))
        assert all(event.account_id == owner.id for event in lifecycle_events)


async def test_delete_cancels_running_ai_but_retains_executor_slot_and_private_business_input(
    identity_engine: AsyncEngine,
) -> None:
    from studymate.infrastructure.ai.models import AiJobRecord, AiSlotRecord
    from tests.integration.ai.test_queue import goal, services, submission

    owner = await actor(identity_engine)
    ai = services(identity_engine)
    source = await goal(identity_engine, owner)
    job = await ai.submit(
        owner.credential,
        submission(source, "PRIVATE_RETAINED_INPUT"),
        IntentKey("before-delete-ai"),
    )
    claimed = await ai.queue.claim()
    assert claimed is not None
    assert claimed.id == job.id
    command = await command_for(identity_engine, owner)
    await deletion(identity_engine)(command)
    async with ai.sessions() as session:
        retained = await session.get(AiJobRecord, job.id)
        slot = await session.get(AiSlotRecord, 1)
        assert retained is not None
        assert retained.state == "cancelled"
        assert "PRIVATE_RETAINED_INPUT" in retained.input_json
        assert slot is not None
        assert slot.job_id == job.id
        assert slot.token == claimed.token
        outcomes = tuple(
            await session.scalars(
                select(ProductEventRecord).where(
                    ProductEventRecord.kind == "ai_job.completed",
                    ProductEventRecord.ai_job_id == job.id,
                )
            )
        )
        assert len(outcomes) == 1
        assert outcomes[0].ai_state == "cancelled"
        assert "PRIVATE_RETAINED_INPUT" not in repr(outcomes[0].__dict__)
        assert await session.scalar(select(func.count()).select_from(LifecycleRevisionRecord)) == 1
    # No subprocess was started: claim models the durable lease only. Keeping the
    # slot occupied proves deletion does not falsely certify physical termination.


async def test_deletion_retains_accepted_conversation_and_request_context(
    identity_engine: AsyncEngine,
) -> None:
    from studymate.infrastructure.persistence.conversation_models import ConversationRecord
    from tests.integration.requests.fixture import action

    sender, recipient, api = await prepared(identity_engine)
    request = await sent(api, sender, recipient)
    accepted = await api.accept(action(recipient, sender, request))
    command = await command_for(identity_engine, sender)
    await deletion(identity_engine)(command)
    async with api.sessions() as session:
        retained = await session.get(ConnectionRequestRecord, request.id)
        conversation = await session.get(ConversationRecord, accepted.conversation.id)
        assert retained is not None
        assert retained.state == "accepted"
        assert retained.preview_id == request.preview_id
        assert conversation is not None
        assert conversation.request_id == request.id
