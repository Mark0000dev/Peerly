from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.idempotency import IntentKey
from studymate.application.ports.http_tracing import HttpExecution
from studymate.domain.ai.jobs import JobState
from studymate.domain.ai.tasks import ClarifiedGoal
from studymate.infrastructure.ai.models import AiJobRecord, AiSlotRecord
from studymate.infrastructure.ai.persistence import cancel_actor_jobs
from studymate.infrastructure.observability.tracing import OtelHttpTracing
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from tests.integration.ai.test_queue import goal, services, submission
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration


async def test_success_and_cancel_each_emit_one_canonical_outcome_with_original_origin(
    ai_engine: AsyncEngine,
) -> None:
    owner = await actor(ai_engine)
    api = services(ai_engine)
    source = await goal(ai_engine, owner)
    request, action = uuid4(), uuid4()
    tracing = OtelHttpTracing()
    with tracing.start(HttpExecution(request, action, "POST", None)):
        accepted = await api.submit(
            owner.credential, submission(source, "PRIVATE_SENTINEL"), IntentKey(str(uuid4()))
        )
    running = await api.queue.claim()
    assert running is not None
    with tracing.start(HttpExecution(uuid4(), uuid4(), "POST", None)):
        await api.queue.complete(running, ClarifiedGoal("PRIVATE_OUTPUT"), stopped=True)
    await api.cancel(owner.credential, accepted.id)
    async with api.sessions() as session:
        event = (
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "ai_job.completed")
            )
        ).one()
        assert event.ai_job_id == accepted.id
        assert event.ai_state == "succeeded"
        assert event.ai_reason is None
        assert event.request_id == request
        assert event.action_id == action
        assert "PRIVATE" not in repr(event.__dict__)
    created = await api.submit(
        owner.credential, submission(source, "Another"), IntentKey(str(uuid4()))
    )
    await api.cancel(owner.credential, created.id)
    await api.cancel(owner.credential, created.id)
    async with api.sessions() as session:
        events = tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "ai_job.completed")
            )
        )
        assert {event.ai_state for event in events} == {"succeeded", "cancelled"}
        assert len(events) == EXPECTED_TWO_JOBS


async def test_admission_expiry_sweep_and_claim_expiry_emit_same_terminal_family(
    ai_engine: AsyncEngine,
) -> None:
    owner = await actor(ai_engine)
    api = services(ai_engine)
    source = await goal(ai_engine, owner)
    for number in range(2):
        await api.submit(
            owner.credential, submission(source, f"Synthetic {number}"), IntentKey(str(uuid4()))
        )
        async with api.sessions.begin() as session:
            await session.execute(
                update(AiJobRecord)
                .where(AiJobRecord.state == "queued")
                .values(
                    created_at=func.clock_timestamp() - timedelta(minutes=10),
                    deadline=func.clock_timestamp() - timedelta(seconds=1),
                )
            )
        if number == 0:
            # Next admission sweeps expiry atomically with its new job.
            continue
        assert await api.queue.claim() is None
    async with api.sessions() as session:
        events = tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "ai_job.completed")
            )
        )
        assert len(events) == EXPECTED_TWO_JOBS
        assert all(event.ai_state == "expired" for event in events)


async def test_recovery_after_deadline_records_expiry_once(ai_engine: AsyncEngine) -> None:
    owner = await actor(ai_engine)
    api = services(ai_engine)
    created = await api.submit(
        owner.credential, submission(await goal(ai_engine, owner)), IntentKey(str(uuid4()))
    )
    running = await api.queue.claim()
    assert running is not None
    assert running.token is not None
    async with api.sessions.begin() as session:
        await session.execute(
            update(AiJobRecord).values(
                created_at=func.clock_timestamp() - timedelta(minutes=10),
                deadline=func.clock_timestamp() - timedelta(seconds=1),
            )
        )
        await session.execute(
            update(AiSlotRecord).values(lease_until=func.clock_timestamp() - timedelta(seconds=1))
        )
    await api.queue.recover_stopped(running.token, running.generation, stopped=True)
    async with api.sessions() as session:
        event = (
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "ai_job.completed")
            )
        ).one()
        assert event.ai_job_id == created.id
        assert event.ai_state == "expired"
        assert event.ai_reason == "executor_lost"


async def test_lifecycle_cancel_and_events_rollback_and_retain_history_on_commit(
    ai_engine: AsyncEngine,
) -> None:
    owner = await actor(ai_engine)
    api = services(ai_engine)
    source = await goal(ai_engine, owner)
    for number in range(2):
        await api.submit(
            owner.credential, submission(source, f"Synthetic {number}"), IntentKey(str(uuid4()))
        )
    running = await api.queue.claim()
    assert running is not None

    async def roll_back_lifecycle() -> None:
        async with api.sessions.begin() as session:
            await session.execute(
                update(AccountRecord)
                .where(AccountRecord.id == owner.id)
                .values(deleted_at=func.clock_timestamp())
            )
            await cancel_actor_jobs(session, owner.id)
            raise RuntimeError("Synthetic rollback")

    with pytest.raises(RuntimeError, match="Synthetic rollback"):
        await roll_back_lifecycle()
    assert (await api.read(owner.credential, running.id)).state == JobState.RUNNING
    async with api.sessions() as session:
        assert not tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "ai_job.completed")
            )
        )
    async with api.sessions.begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == owner.id)
            .values(deleted_at=func.clock_timestamp())
        )
        await cancel_actor_jobs(session, owner.id)
    async with api.sessions() as session:
        events = tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "ai_job.completed")
            )
        )
        assert len(events) == EXPECTED_TWO_JOBS
        assert all(event.ai_state == "cancelled" and event.ai_reason is None for event in events)
        assert (await session.scalars(select(AiSlotRecord.token))).one() == running.token
        assert (
            len(tuple(await session.scalars(select(AiJobRecord.input_json)))) == EXPECTED_TWO_JOBS
        )


EXPECTED_TWO_JOBS = 2
