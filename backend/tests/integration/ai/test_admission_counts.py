from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.engine import ExecutionContext
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlalchemy.sql.elements import FunctionFilter
from sqlalchemy.sql.selectable import CTE, Select
from sqlalchemy.sql.visitors import iterate

from studymate.application.ai.policy import AdmissionPolicy
from studymate.application.ai.ports import AiQuotaError, AiUnavailableError
from studymate.application.ai.student import SubmitStudentJob
from studymate.application.idempotency import IntentKey
from studymate.domain.ai.jobs import JobState
from studymate.domain.ai.tasks import AiKind, AiTask, ClarifyGoal, Source, TriageReport
from studymate.infrastructure.ai.codec import TASK_CODEC
from studymate.infrastructure.ai.models import AiBudgetRecord, AiIntentRecord, AiJobRecord
from studymate.infrastructure.ai.persistence import SqlAiUnitOfWork
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.ai.runtime.facts import fake_runtime_ready
from tests.integration.ai.test_queue import VERSIONS, goal, submission
from tests.integration.conftest import database_url as database_url
from tests.integration.conftest import engine as engine
from tests.integration.conftest import identity_engine as identity_engine
from tests.integration.student_actor import Actor, actor


@dataclass(frozen=True, slots=True)
class RetainedJob:
    own: bool = False
    internal: bool = False
    state: JobState = JobState.QUEUED
    expired: bool = False


@dataclass(frozen=True, slots=True)
class CapacityCase:
    jobs: tuple[RetainedJob, ...]
    failure: type[AiUnavailableError] | type[AiQuotaError] | None = None


CASES = (
    CapacityCase(()),
    CapacityCase((RetainedJob(state=JobState.RUNNING),)),
    CapacityCase((RetainedJob(),), AiUnavailableError),
    CapacityCase((RetainedJob(internal=True),)),
    CapacityCase((RetainedJob(internal=True), RetainedJob(internal=True)), AiUnavailableError),
    CapacityCase((RetainedJob(own=True, state=JobState.RUNNING),), AiQuotaError),
    CapacityCase((RetainedJob(own=True),), AiUnavailableError),
    CapacityCase((RetainedJob(own=True, expired=True),)),
    CapacityCase((RetainedJob(own=True, state=JobState.RUNNING, expired=True),), AiQuotaError),
    CapacityCase(
        (
            RetainedJob(own=True, state=JobState.CANCELLED),
            RetainedJob(own=True, state=JobState.FAILED),
            RetainedJob(own=True, state=JobState.EXPIRED),
        )
    ),
)


def record(
    owner: Actor, other: Actor, source: Source, other_source: Source, fixture: RetainedJob
) -> AiJobRecord:
    now = datetime.now(UTC)
    selected = source if fixture.own else other_source
    task: AiTask = (
        TriageReport(selected, "Synthetic retained support report")
        if fixture.internal
        else ClarifyGoal(selected, "Synthetic retained quota fixture")
    )
    return AiJobRecord(
        id=uuid4(),
        actor_id=owner.id if fixture.own else other.id,
        kind=AiKind.TRIAGE_REPORT.value if fixture.internal else AiKind.CLARIFY_GOAL.value,
        source_id=selected.id,
        source_version=selected.version,
        digest=uuid4().bytes + uuid4().bytes,
        input_json=TASK_CODEC.dump_json(task).decode(),
        model=VERSIONS.model,
        prompt=VERSIONS.prompt,
        schema_version=VERSIONS.schema,
        adapter=VERSIONS.adapter,
        state=fixture.state.value,
        created_at=now - timedelta(minutes=10) if fixture.expired else now,
        deadline=now - timedelta(seconds=1) if fixture.expired else now + timedelta(minutes=5),
        not_before=now,
        attempts=1 if fixture.state == JobState.RUNNING else 0,
        generation=1 if fixture.state == JobState.RUNNING else 0,
        token=uuid4() if fixture.state == JobState.RUNNING else None,
    )


@dataclass(slots=True)
class AggregateQueries:
    count: int = 0

    def before(self, *, context: ExecutionContext, **_ignored: object) -> None:
        compiled = context.compiled.statement if context.compiled is not None else None
        if isinstance(compiled, Select) and (
            any(isinstance(column, FunctionFilter) for column in compiled.selected_columns)
            or any(
                isinstance(node, CTE) and node.name == "student_admission_clock"
                for node in iterate(compiled)
            )
        ):
            self.count += 1


@pytest.mark.parametrize(
    "case",
    CASES,
    ids=(
        "empty",
        "other-running",
        "other-interactive-reserve",
        "other-internal-reserve",
        "global-internal-full",
        "own-running-quota",
        "capacity-before-actor-quota",
        "expired-queued-reclaimed",
        "expired-running-retained",
        "terminal-not-outstanding",
    ),
)
async def test_actual_admission_retains_capacity_quota_expiry_and_error_precedence(
    identity_engine: AsyncEngine,
    case: CapacityCase,
) -> None:
    owner, other = await actor(identity_engine), await actor(identity_engine)
    source = await goal(identity_engine, owner)
    other_source = await goal(identity_engine, other)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    seeded = tuple(record(owner, other, source, other_source, fixture) for fixture in case.jobs)
    async with sessions.begin() as session:
        session.add_all(seeded)
    submit = SubmitStudentJob(
        SqlAiUnitOfWork(
            sessions, AdmissionPolicy(queue_limit=2, internal_reserve=1, student_outstanding=1)
        ),
        Sha256SessionHasher(),
        HmacIntentFingerprinter(b"x" * 32),
        VERSIONS,
    )
    observed = AggregateQueries()
    async with fake_runtime_ready(identity_engine, VERSIONS):
        event.listen(
            identity_engine.sync_engine, "before_cursor_execute", observed.before, named=True
        )
        try:
            if case.failure is None:
                created = await submit(
                    owner.credential, submission(source), IntentKey(str(uuid4()))
                )
                assert created.state == JobState.QUEUED
            else:
                with pytest.raises(case.failure):
                    await submit(owner.credential, submission(source), IntentKey(str(uuid4())))
        finally:
            event.remove(identity_engine.sync_engine, "before_cursor_execute", observed.before)
    # This is a performance acceptance constraint: one SQL round trip for all
    # three independent population counts, not three serial WAN round trips.
    assert observed.count == 1
    async with sessions() as session:
        intents = tuple(await session.scalars(select(AiIntentRecord)))
        budget = await session.get(AiBudgetRecord, owner.id)
        rows = tuple(await session.scalars(select(AiJobRecord)))
    if case.failure is None:
        assert len(intents) == 1
        assert budget is not None
        assert budget.tokens == AdmissionPolicy().bucket_capacity - 1
        for seeded_row, fixture in zip(seeded, case.jobs, strict=True):
            stored = next(row for row in rows if row.id == seeded_row.id)
            expected = (
                JobState.EXPIRED
                if fixture.expired and fixture.state == JobState.QUEUED
                else fixture.state
            )
            assert stored.state == expected.value
    else:
        assert not intents
        assert budget is None
        assert len(rows) == len(case.jobs)
