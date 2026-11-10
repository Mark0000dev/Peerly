from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import DateTime, cast, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

import studymate.infrastructure.persistence.product_events as product_events_module
from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import SessionCredential
from studymate.domain.ai.jobs import AiJob, Failure, JobState
from studymate.domain.ai.tasks import ClarifiedGoal
from studymate.infrastructure.ai.models import AiJobRecord
from studymate.infrastructure.ai.persistence import save_state
from studymate.infrastructure.observability.origin import ExecutionOrigin
from studymate.infrastructure.persistence.identity_models import SessionRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_ai_terminal
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.ai.runtime.facts import fake_runtime_ready
from tests.integration.ai.test_queue import VERSIONS, Services, goal, services, submission
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration


@pytest.fixture
async def controlled_ai_runtime(identity_engine: AsyncEngine) -> AsyncIterator[None]:
    # These tests submit to a controlled fake executor, not a configured provider.
    async with fake_runtime_ready(identity_engine, VERSIONS):
        yield


async def prepared(engine: AsyncEngine) -> tuple[Services, AiJob, ExecutionOrigin]:
    owner = await actor(engine)
    source = await goal(engine, owner)
    api = services(engine)
    job = await api.submit(owner.credential, submission(source), IntentKey(str(uuid4())))
    origin = ExecutionOrigin(uuid4(), uuid4(), "a" * 32, "b" * 16)
    async with api.sessions.begin() as session:
        await session.execute(
            update(AiJobRecord)
            .where(AiJobRecord.id == job.id)
            .values(
                request_id=origin.request_id,
                action_id=origin.action_id,
                trace_id=origin.trace_id,
                span_id=origin.span_id,
            )
        )
    return api, job, origin


@pytest.mark.parametrize("state", [JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED])
@pytest.mark.usefixtures("controlled_ai_runtime")
async def test_ai_terminal_event_is_once_only_and_uses_the_stored_submission_origin(
    identity_engine: AsyncEngine,
    state: JobState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, queued, origin = await prepared(identity_engine)
    unrelated = ExecutionOrigin(uuid4(), None, None, None)
    monkeypatch.setattr(product_events_module, "current_origin", lambda: unrelated)
    if state == JobState.CANCELLED:
        terminal = await api.cancel((await actor_credential(identity_engine, queued)), queued.id)
    else:
        claimed = await api.queue.claim()
        assert claimed is not None
        terminal = await api.queue.complete(
            claimed,
            ClarifiedGoal("Synthetic retained private output")
            if state == JobState.SUCCEEDED
            else Failure.INVALID_INPUT,
            stopped=True,
        )
    assert terminal.state == state
    async with api.sessions.begin() as session:
        await record_ai_terminal(session, terminal, datetime.now(UTC), origin)
    async with api.sessions.begin() as session:
        await record_ai_terminal(session, terminal, datetime.now(UTC), origin)
    async with api.sessions() as session:
        events = (
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "ai_job.completed")
            )
        ).all()
        assert len(events) == 1
        event = events[0]
        assert event.ai_job_id == queued.id
        assert event.account_id == queued.actor_id
        assert event.ai_kind == "clarify_goal"
        assert event.ai_state == state.value
        assert event.ai_reason == ("invalid_input" if state == JobState.FAILED else None)
        assert event.request_id == origin.request_id
        assert event.action_id == origin.action_id
        assert event.trace_id == origin.trace_id
        assert event.span_id == origin.span_id
        assert event.goal_id is None
        assert event.profile_version is None


async def actor_credential(engine: AsyncEngine, job: AiJob) -> SessionCredential:
    credential = SessionCredential("s" * 43)
    async with async_sessionmaker(engine).begin() as session:
        # Session validity uses the database clock, including its lower bound.
        issued_at = (
            await session.execute(select(cast(func.clock_timestamp(), DateTime(timezone=True))))
        ).scalar_one()
        session.add(
            SessionRecord(
                id=uuid4(),
                account_id=job.actor_id,
                issued_at=issued_at,
                expires_at=issued_at + timedelta(hours=1),
                secret_digest=await Sha256SessionHasher().digest(credential),
            )
        )
    return credential


@pytest.mark.usefixtures("controlled_ai_runtime")
async def test_ai_event_requires_a_real_terminal_source_fact(
    identity_engine: AsyncEngine,
) -> None:
    api, queued, origin = await prepared(identity_engine)
    async with api.sessions.begin() as session:
        with pytest.raises(ValueError, match="terminal"):
            await record_ai_terminal(session, queued, datetime.now(UTC), origin)
    async with api.sessions.begin() as session:
        with pytest.raises(RuntimeError, match="stored source"):
            await record_ai_terminal(
                session, replace(queued, state=JobState.CANCELLED), datetime.now(UTC), origin
            )
    async with api.sessions() as session:
        assert (
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "ai_job.completed")
            )
        ).all() == []


@pytest.mark.usefixtures("controlled_ai_runtime")
async def test_ai_terminal_transition_and_canonical_event_roll_back_together(
    identity_engine: AsyncEngine,
) -> None:
    api, queued, origin = await prepared(identity_engine)

    async def interrupted_terminal_write() -> None:
        async with api.sessions.begin() as session:
            record = await session.get(AiJobRecord, queued.id)
            assert record is not None
            terminal = replace(queued, state=JobState.CANCELLED)
            save_state(record, terminal)
            await record_ai_terminal(session, terminal, datetime.now(UTC), origin)
            raise RuntimeError("Synthetic interruption before commit")

    with pytest.raises(RuntimeError, match="Synthetic interruption"):
        await interrupted_terminal_write()
    async with api.sessions() as session:
        record = await session.get(AiJobRecord, queued.id)
        assert record is not None
        assert record.state == "queued"
        assert (
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "ai_job.completed")
            )
        ).all() == []
