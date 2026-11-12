import asyncio
from dataclasses import dataclass, replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.ai.ports import (
    AiJobNotFoundError,
    AiQuotaError,
    AiSourceUnavailableError,
    AiUnavailableError,
    StudentSubmission,
)
from studymate.application.ai.student import CancelStudentJob, ReadStudentJob, SubmitStudentJob
from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.application.profiles.goals import SaveGoalCommand, SaveOwnGoal
from studymate.domain.ai.jobs import AiJob, Failure, JobState, LeaseLostError, Versions
from studymate.domain.ai.tasks import AiKind, ClarifiedGoal, Source, TriageReport
from studymate.domain.study_context import CustomSubjectRef, GoalContent
from studymate.infrastructure.ai.models import (
    AiAttemptRecord,
    AiBudgetRecord,
    AiIntentRecord,
    AiJobRecord,
    AiSlotRecord,
)
from studymate.infrastructure.ai.persistence import SqlAiUnitOfWork
from studymate.infrastructure.ai.queue import SqlAiQueue
from studymate.infrastructure.persistence.goals import SqlGoalUnitOfWork
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
    SessionRecord,
)
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.student_actor import Actor, actor

GLOBAL_CAPACITY = 100
INTERACTIVE_CAPACITY = 90

EXPECTED_TOKENS_AFTER_ONE = 4
EXPECTED_INTENT_ALIASES = 2
EXPECTED_OUTSTANDING = 2
RACE_SUBMISSIONS = 12

pytestmark = pytest.mark.integration
VERSIONS = Versions("synthetic-model")


@dataclass(frozen=True, slots=True)
class Services:
    sessions: async_sessionmaker[AsyncSession]
    submit: SubmitStudentJob
    read: ReadStudentJob
    cancel: CancelStudentJob
    queue: SqlAiQueue


def services(engine: AsyncEngine) -> Services:
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    uow = SqlAiUnitOfWork(sessions)
    hasher = Sha256SessionHasher()
    return Services(
        sessions,
        SubmitStudentJob(uow, hasher, HmacIntentFingerprinter(b"x" * 32), VERSIONS),
        ReadStudentJob(uow, hasher),
        CancelStudentJob(uow, hasher),
        SqlAiQueue(sessions),
    )


async def goal(engine: AsyncEngine, owner: Actor) -> Source:
    saved = await SaveOwnGoal(
        SqlGoalUnitOfWork(async_sessionmaker(engine, expire_on_commit=False)),
        Sha256SessionHasher(),
        HmacIntentFingerprinter(b"x" * 32),
    )(
        SaveGoalCommand(
            owner.credential,
            GoalContent(CustomSubjectRef("Synthetic subject")),
            None,
            0,
            IntentKey(str(uuid4())),
        )
    )
    return Source(saved.goal.id, saved.goal.version)


def submission(source: Source, text: str = "Synthetic private goal") -> StudentSubmission:
    return StudentSubmission(AiKind.CLARIFY_GOAL, source, text)


async def test_idempotency_coalescing_and_payload_conflict_do_not_spend_tokens(
    ai_engine: AsyncEngine,
) -> None:
    owner = await actor(ai_engine)
    source = await goal(ai_engine, owner)
    api = services(ai_engine)
    key = IntentKey(str(uuid4()))

    async def create() -> AiJob:
        return await api.submit(owner.credential, submission(source), key)

    first, replay = await asyncio.gather(create(), create())
    assert first.id == replay.id
    alias = await api.submit(owner.credential, submission(source), IntentKey(str(uuid4())))
    assert alias.id == first.id
    with pytest.raises(IdempotencyConflictError):
        await api.submit(owner.credential, submission(source, "Changed"), key)
    async with api.sessions() as session:
        assert (
            await session.scalars(select(AiBudgetRecord.tokens))
        ).one() == EXPECTED_TOKENS_AFTER_ONE
        assert (
            await session.scalars(select(func.count()).select_from(AiIntentRecord))
        ).one() == EXPECTED_INTENT_ALIASES
    assert await api.read(owner.credential, first.id) == first


async def test_actor_admission_race_has_exactly_two_winners(ai_engine: AsyncEngine) -> None:
    owner = await actor(ai_engine)
    source = await goal(ai_engine, owner)
    api = services(ai_engine)

    async def create(number: int) -> AiJob | AiQuotaError:
        try:
            return await api.submit(
                owner.credential, submission(source, f"Synthetic {number}"), IntentKey(str(uuid4()))
            )
        except AiQuotaError as error:
            return error

    outcomes = await asyncio.gather(*(create(number) for number in range(RACE_SUBMISSIONS)))
    assert sum(isinstance(value, AiJob) for value in outcomes) == EXPECTED_OUTSTANDING
    assert (
        sum(isinstance(value, AiQuotaError) for value in outcomes)
        == RACE_SUBMISSIONS - EXPECTED_OUTSTANDING
    )


async def test_running_cancel_retains_slot_until_stop_and_discards_late_result(
    ai_engine: AsyncEngine,
) -> None:
    owner = await actor(ai_engine)
    api = services(ai_engine)
    initial = await api.submit(
        owner.credential, submission(await goal(ai_engine, owner)), IntentKey(str(uuid4()))
    )
    running = await api.queue.claim()
    assert running is not None
    assert running.id == initial.id
    assert await api.queue.heartbeat(running)
    cancelled = await api.cancel(owner.credential, running.id)
    assert cancelled.state == JobState.CANCELLED
    assert not await api.queue.heartbeat(running)
    assert await api.queue.claim() is None
    with pytest.raises(ValueError, match="Physical"):
        await api.queue.complete(running, ClarifiedGoal("Late private"), stopped=False)
    finished = await api.queue.complete(running, ClarifiedGoal("Late private"), stopped=True)
    assert finished.state == JobState.CANCELLED
    assert finished.result is None
    with pytest.raises(LeaseLostError):
        await api.queue.complete(running, ClarifiedGoal("Late"), stopped=True)
    async with api.sessions() as session:
        attempt = (await session.scalars(select(AiAttemptRecord))).one()
        assert attempt.ended_at is not None


async def test_expired_lease_requires_confirmed_stop_and_fences_old_generation(
    ai_engine: AsyncEngine,
) -> None:
    owner = await actor(ai_engine)
    api = services(ai_engine)
    await api.submit(
        owner.credential, submission(await goal(ai_engine, owner)), IntentKey(str(uuid4()))
    )
    running = await api.queue.claim()
    assert running is not None
    assert running.token is not None
    async with api.sessions.begin() as session:
        await session.execute(
            update(AiSlotRecord).values(lease_until=func.clock_timestamp() - timedelta(seconds=1))
        )
    assert await api.queue.claim() is None
    with pytest.raises(LeaseLostError):
        await api.queue.heartbeat(running)
    with pytest.raises(LeaseLostError):
        await api.queue.complete(running, ClarifiedGoal("Discard"), stopped=True)
    with pytest.raises(ValueError, match="Uncertain"):
        await api.queue.recover_stopped(running.token, running.generation, stopped=False)
    await api.queue.recover_stopped(running.token, running.generation, stopped=True)
    async with api.sessions.begin() as session:
        await session.execute(update(AiJobRecord).values(not_before=func.clock_timestamp()))
    replacement = await api.queue.claim()
    assert replacement is not None
    assert replacement.generation > running.generation
    with pytest.raises(LeaseLostError):
        await api.queue.complete(running, ClarifiedGoal("Discard"), stopped=True)
    assert (
        await api.queue.complete(replacement, ClarifiedGoal("Saved once"), stopped=True)
    ).state == JobState.SUCCEEDED
    assert (await api.read(owner.credential, running.id)).result == ClarifiedGoal("Saved once")


async def test_competing_workers_claim_only_one_and_completion_is_once(
    ai_engine: AsyncEngine,
) -> None:
    owner = await actor(ai_engine)
    api = services(ai_engine)
    await api.submit(
        owner.credential, submission(await goal(ai_engine, owner)), IntentKey(str(uuid4()))
    )
    claims = await asyncio.gather(*(api.queue.claim() for _ in range(8)))
    winners = [value for value in claims if value is not None]
    assert len(winners) == 1

    async def finish() -> AiJob | LeaseLostError:
        try:
            return await api.queue.complete(winners[0], ClarifiedGoal("Only result"), stopped=True)
        except LeaseLostError as error:
            return error

    outcomes = await asyncio.gather(finish(), finish())
    assert sum(isinstance(value, AiJob) for value in outcomes) == 1
    assert sum(isinstance(value, LeaseLostError) for value in outcomes) == 1


@pytest.mark.parametrize("restriction", ["unverified", "revoked", "banned", "deleted", "expired"])
async def test_student_guard_applies_to_submit_read_cancel_and_retains_history(
    ai_engine: AsyncEngine, restriction: str
) -> None:
    owner = await actor(ai_engine)
    api = services(ai_engine)
    source = await goal(ai_engine, owner)
    created = await api.submit(owner.credential, submission(source), IntentKey(str(uuid4())))
    async with api.sessions.begin() as session:
        if restriction == "unverified":
            from sqlalchemy import delete

            await session.execute(delete(InstitutionalBindingRecord))
        elif restriction == "revoked":
            await session.execute(
                update(InstitutionalBindingRecord).values(revoked_at=func.clock_timestamp())
            )
        elif restriction in {"banned", "deleted"}:
            await session.execute(
                update(AccountRecord).values({restriction + "_at": func.clock_timestamp()})
            )
        else:
            await session.execute(
                update(SessionRecord).values(
                    expires_at=func.clock_timestamp() - timedelta(seconds=1)
                )
            )
    denied = (
        UnauthenticatedError if restriction in {"deleted", "expired"} else StudentActionDeniedError
    )
    with pytest.raises(denied):
        await api.submit(owner.credential, submission(source), IntentKey(str(uuid4())))
    with pytest.raises(denied):
        await api.read(owner.credential, created.id)
    with pytest.raises(denied):
        await api.cancel(owner.credential, created.id)
    async with api.sessions() as session:
        assert (await session.scalars(select(AiJobRecord.input_json))).one()


async def test_source_ownership_unknown_jobs_and_stale_revision(ai_engine: AsyncEngine) -> None:
    owner, other = await actor(ai_engine), await actor(ai_engine)
    api = services(ai_engine)
    source = await goal(ai_engine, owner)
    with pytest.raises(AiSourceUnavailableError):
        await api.submit(other.credential, submission(source), IntentKey(str(uuid4())))
    with pytest.raises(AiSourceUnavailableError):
        await api.submit(
            owner.credential, submission(replace(source, version=2)), IntentKey(str(uuid4()))
        )
    created = await api.submit(owner.credential, submission(source), IntentKey(str(uuid4())))
    for job_id in (created.id, uuid4()):
        with pytest.raises(AiJobNotFoundError):
            await api.read(other.credential, job_id)
        with pytest.raises(AiJobNotFoundError):
            await api.cancel(other.credential, job_id)


async def test_auth_circuit_and_rate_pause_are_durable(ai_engine: AsyncEngine) -> None:
    owner = await actor(ai_engine)
    api = services(ai_engine)
    source = await goal(ai_engine, owner)
    await api.submit(owner.credential, submission(source), IntentKey(str(uuid4())))
    running = await api.queue.claim()
    assert running is not None
    await api.queue.complete(
        running, Failure.RATE_LIMIT, stopped=True, retry_after=timedelta(seconds=30)
    )
    assert await api.queue.claim() is None
    with pytest.raises(AiUnavailableError):
        await api.submit(owner.credential, submission(source, "Another"), IntentKey(str(uuid4())))
    async with api.sessions.begin() as session:
        await session.execute(update(AiSlotRecord).values(paused_until=None))
        await session.execute(update(AiJobRecord).values(not_before=func.clock_timestamp()))
    running = await api.queue.claim()
    assert running is not None
    result = await api.queue.complete(running, Failure.AUTH, stopped=True)
    assert result.state == JobState.FAILED
    assert await api.queue.claim() is None
    with pytest.raises(AiUnavailableError):
        await api.submit(owner.credential, submission(source), IntentKey(str(uuid4())))


async def test_database_rejects_result_without_success_and_cross_owner_intents(
    ai_engine: AsyncEngine,
) -> None:
    owner, other = await actor(ai_engine), await actor(ai_engine)
    api = services(ai_engine)
    created = await api.submit(
        owner.credential, submission(await goal(ai_engine, owner)), IntentKey(str(uuid4()))
    )
    with pytest.raises(IntegrityError):
        async with api.sessions.begin() as session:
            await session.execute(
                update(AiJobRecord).values(result_json='{"suggestion":"uncommitted"}')
            )
    with pytest.raises(IntegrityError):
        async with api.sessions.begin() as session:
            session.add(
                AiIntentRecord(
                    actor_id=other.id,
                    kind=AiKind.CLARIFY_GOAL.value,
                    key="synthetic-key",
                    job_id=created.id,
                    digest=b"x" * 32,
                )
            )


async def test_token_budget_persists_through_cancellation_and_refills(
    ai_engine: AsyncEngine,
) -> None:
    owner = await actor(ai_engine)
    api = services(ai_engine)
    source = await goal(ai_engine, owner)
    for number in range(5):
        created = await api.submit(
            owner.credential, submission(source, f"Synthetic {number}"), IntentKey(str(uuid4()))
        )
        await api.cancel(owner.credential, created.id)
    with pytest.raises(AiQuotaError):
        await api.submit(owner.credential, submission(source, "Sixth"), IntentKey(str(uuid4())))
    async with api.sessions.begin() as session:
        await session.execute(
            update(AiBudgetRecord).values(
                refilled_at=func.clock_timestamp() - timedelta(seconds=61)
            )
        )
    assert (
        await api.submit(owner.credential, submission(source, "Refilled"), IntentKey(str(uuid4())))
    ).state == JobState.QUEUED


async def test_queued_expiry_is_reclaimed_for_admission_and_running_expiry_discards_output(
    ai_engine: AsyncEngine,
) -> None:
    owner = await actor(ai_engine)
    api = services(ai_engine)
    source = await goal(ai_engine, owner)
    created = await api.submit(owner.credential, submission(source), IntentKey(str(uuid4())))
    async with api.sessions.begin() as session:
        await session.execute(
            update(AiJobRecord).values(
                created_at=func.clock_timestamp() - timedelta(minutes=10),
                deadline=func.clock_timestamp() - timedelta(seconds=1),
            )
        )
    assert await api.queue.claim() is None
    assert (await api.read(owner.credential, created.id)).state == JobState.EXPIRED
    await api.submit(owner.credential, submission(source, "Second"), IntentKey(str(uuid4())))
    running = await api.queue.claim()
    assert running is not None
    async with api.sessions.begin() as session:
        await session.execute(
            update(AiJobRecord)
            .where(AiJobRecord.id == running.id)
            .values(
                created_at=func.clock_timestamp() - timedelta(minutes=10),
                deadline=func.clock_timestamp() - timedelta(seconds=1),
            )
        )
    assert (
        await api.queue.complete(running, ClarifiedGoal("Late"), stopped=True)
    ).state == JobState.EXPIRED


@pytest.mark.parametrize("phase", ["claim", "completion"])
async def test_source_edit_cannot_apply_or_execute_old_revision(
    ai_engine: AsyncEngine, phase: str
) -> None:
    owner = await actor(ai_engine)
    api = services(ai_engine)
    source = await goal(ai_engine, owner)
    key = IntentKey(str(uuid4()))
    created = await api.submit(owner.credential, submission(source), key)
    running = await api.queue.claim() if phase == "completion" else None
    await SaveOwnGoal(
        SqlGoalUnitOfWork(api.sessions), Sha256SessionHasher(), HmacIntentFingerprinter(b"x" * 32)
    )(
        SaveGoalCommand(
            owner.credential,
            GoalContent(CustomSubjectRef("Edited synthetic")),
            source.id,
            source.version,
            IntentKey(str(uuid4())),
        )
    )
    assert (await api.submit(owner.credential, submission(source), key)).id == created.id
    if phase == "claim":
        assert await api.queue.claim() is None
    else:
        assert running is not None
        await api.queue.complete(running, ClarifiedGoal("Stale advice"), stopped=True)
    persisted = await api.read(owner.credential, created.id)
    assert persisted.state == JobState.FAILED
    assert persisted.failure == Failure.STALE_SOURCE
    assert persisted.result is None


async def test_cancel_completion_race_has_stable_terminal_outcome(ai_engine: AsyncEngine) -> None:
    owner = await actor(ai_engine)
    api = services(ai_engine)
    await api.submit(
        owner.credential, submission(await goal(ai_engine, owner)), IntentKey(str(uuid4()))
    )
    running = await api.queue.claim()
    assert running is not None
    await asyncio.gather(
        api.cancel(owner.credential, running.id),
        api.queue.complete(running, ClarifiedGoal("Racing"), stopped=True),
    )
    first = await api.read(owner.credential, running.id)
    assert first.state in {JobState.CANCELLED, JobState.SUCCEEDED}
    assert await api.cancel(owner.credential, running.id) == first


async def test_account_deletion_before_completion_retains_business_input_and_attempt(
    ai_engine: AsyncEngine,
) -> None:
    owner = await actor(ai_engine)
    api = services(ai_engine)
    await api.submit(
        owner.credential, submission(await goal(ai_engine, owner)), IntentKey(str(uuid4()))
    )
    running = await api.queue.claim()
    assert running is not None
    async with api.sessions.begin() as session:
        await session.execute(update(AccountRecord).values(deleted_at=func.clock_timestamp()))
    value = await api.queue.complete(running, ClarifiedGoal("Discarded"), stopped=True)
    assert value.state == JobState.FAILED
    assert value.failure == Failure.ACCOUNT
    async with api.sessions() as session:
        assert (await session.scalars(select(AiJobRecord.input_json))).one()
        assert (await session.scalars(select(AiAttemptRecord.ended_at))).one() is not None


async def test_global_admission_race_preserves_reserved_internal_capacity(
    ai_engine: AsyncEngine,
) -> None:
    # Exercise admission transactions directly, with clearly synthetic prevalidated tasks.
    # These are NOT a report authorization or student API test.
    from studymate.application.ai.ports import Admission
    from studymate.domain.ai.tasks import ClarifyGoal, TriageReport

    owners = [await actor(ai_engine) for _ in range(55)]
    sessions = services(ai_engine).sessions

    async def admit(number: int, *, internal: bool = False) -> AiJob | AiUnavailableError:
        owner = owners[number // 2]
        task = (
            TriageReport(Source(uuid4(), 1), "Synthetic selected evidence")
            if internal
            else ClarifyGoal(Source(uuid4(), 1), "Synthetic explicit text")
        )
        try:
            async with SqlAiUnitOfWork(sessions).transaction() as transaction:
                return await transaction.admit(
                    Admission(owner.id, task, IntentKey(str(uuid4())), uuid4().bytes * 2, VERSIONS),
                    await transaction.now(),
                )
        except AiUnavailableError as error:
            return error

    # Keep pool bounded: bursts of ten compete for the same admission row.
    outcomes: list[AiJob | AiUnavailableError] = []
    for start in range(0, 100, 10):
        outcomes.extend(
            await asyncio.gather(*(admit(number) for number in range(start, start + 10)))
        )
    assert sum(isinstance(value, AiJob) for value in outcomes) == INTERACTIVE_CAPACITY
    internal = await asyncio.gather(*(admit(number, internal=True) for number in range(100, 110)))
    assert all(isinstance(value, AiJob) for value in internal)
    assert isinstance(await admit(108, internal=True), AiUnavailableError)
    async with sessions() as session:
        assert (
            await session.scalars(select(func.count()).select_from(AiJobRecord))
        ).one() == GLOBAL_CAPACITY


@dataclass(frozen=True, slots=True)
class SyntheticReportEligibility:
    async def check(
        self, session: AsyncSession, job: AiJob, *, lock: bool = True
    ) -> Failure | None:
        # Controlled permission/source boundary only; production uses actual report authority.
        if not lock or not session.in_transaction() or job.actor_id.int <= 0:
            return Failure.ACCOUNT
        if (
            not isinstance(job.task, TriageReport)
            or job.task.evidence != "Synthetic selected evidence"
        ):
            return Failure.STALE_SOURCE
        return None


async def test_fairness_round_robins_actors_and_services_due_internal_after_four(
    ai_engine: AsyncEngine,
) -> None:
    from studymate.application.ai.ports import Admission
    from studymate.domain.ai.tasks import Priority, ReportTriage

    api = services(ai_engine)
    owners = [await actor(ai_engine) for _ in range(5)]
    sources = [await goal(ai_engine, owner) for owner in owners]
    expected: list[UUID] = []
    for owner, source in zip(owners, sources, strict=True):
        await api.submit(
            owner.credential, submission(source, "First synthetic"), IntentKey(str(uuid4()))
        )
        await api.submit(
            owner.credential, submission(source, "Second synthetic"), IntentKey(str(uuid4()))
        )
        expected.append(owner.id)
    operator = await actor(ai_engine)
    report = TriageReport(Source(uuid4(), 1), "Synthetic selected evidence")
    async with SqlAiUnitOfWork(api.sessions).transaction() as transaction:
        internal = await transaction.admit(
            Admission(operator.id, report, IntentKey(str(uuid4())), b"z" * 32, VERSIONS),
            await transaction.now(),
        )
    queue = SqlAiQueue(api.sessions, SyntheticReportEligibility())
    seen: list[UUID] = []
    for _ in range(4):
        current = await queue.claim()
        assert current is not None
        assert current.actor_id not in seen
        seen.append(current.actor_id)
        await queue.complete(current, ClarifiedGoal("Editable"), stopped=True)
    due = await queue.claim()
    assert due is not None
    assert due.id == internal.id
    await queue.complete(due, ReportTriage(Priority.NORMAL, "Human review"), stopped=True)
    fifth = await queue.claim()
    assert fifth is not None
    assert fifth.actor_id == expected[-1]
    await queue.complete(fifth, ClarifiedGoal("Editable"), stopped=True)


async def test_delayed_retry_does_not_block_another_actor_and_retry_has_new_fence(
    ai_engine: AsyncEngine,
) -> None:
    owner, other = await actor(ai_engine), await actor(ai_engine)
    api = services(ai_engine)
    await api.submit(
        owner.credential, submission(await goal(ai_engine, owner)), IntentKey(str(uuid4()))
    )
    await api.submit(
        other.credential, submission(await goal(ai_engine, other)), IntentKey(str(uuid4()))
    )
    first = await api.queue.claim()
    assert first is not None
    retry = await api.queue.complete(
        first, Failure.INVALID_OUTPUT, stopped=True, retry_after=timedelta(seconds=30)
    )
    assert retry.state == JobState.QUEUED
    second = await api.queue.claim()
    assert second is not None
    assert second.actor_id == other.id
    await api.queue.complete(second, ClarifiedGoal("Other actor advice"), stopped=True)
    async with api.sessions.begin() as session:
        await session.execute(
            update(AiJobRecord)
            .where(AiJobRecord.id == first.id)
            .values(not_before=func.clock_timestamp())
        )
    repeated = await api.queue.claim()
    assert repeated is not None
    assert repeated.token != first.token
    terminal = await api.queue.complete(repeated, Failure.INVALID_OUTPUT, stopped=True)
    assert terminal.state == JobState.FAILED
    assert terminal.attempts == EXPECTED_OUTSTANDING


async def test_unwired_report_permission_fails_closed(ai_engine: AsyncEngine) -> None:
    from studymate.application.ai.ports import Admission

    owner = await actor(ai_engine)
    api = services(ai_engine)
    async with SqlAiUnitOfWork(api.sessions).transaction() as transaction:
        internal = await transaction.admit(
            Admission(
                owner.id,
                TriageReport(Source(uuid4(), 1), "Synthetic selected evidence"),
                IntentKey(str(uuid4())),
                b"z" * 32,
                VERSIONS,
            ),
            await transaction.now(),
        )
    assert await api.queue.claim() is None
    with pytest.raises(AiJobNotFoundError):
        await api.read(owner.credential, internal.id)
    with pytest.raises(AiJobNotFoundError):
        await api.cancel(owner.credential, internal.id)


async def test_photo_advice_uses_owned_ready_reference_during_onboarding(
    ai_engine: AsyncEngine,
) -> None:
    from studymate.domain.ai.tasks import AssessPhoto, Observation, PhotoAssessment
    from studymate.infrastructure.persistence.media_uploads import SqlMediaTransaction
    from tests.integration.onboarding_fixture import ready_setup

    owner, other = await actor(ai_engine), await actor(ai_engine)
    await ready_setup(ai_engine, owner.credential)
    api = services(ai_engine)
    async with api.sessions() as session:
        photo = await SqlMediaTransaction(session).current_photo(owner.id)
    assert photo is not None
    request = StudentSubmission(AiKind.ASSESS_PHOTO, Source(photo.upload_id, photo.version))
    with pytest.raises(AiSourceUnavailableError):
        await api.submit(other.credential, request, IntentKey(str(uuid4())))
    with pytest.raises(AiSourceUnavailableError):
        await api.submit(
            owner.credential, replace(request, source=Source(uuid4(), 1)), IntentKey(str(uuid4()))
        )
    created = await api.submit(owner.credential, request, IntentKey(str(uuid4())))
    assert isinstance(created.task, AssessPhoto)
    assert created.task.reference.attempt_id is not None
    running = await api.queue.claim()
    assert running is not None
    advisory = PhotoAssessment(Observation.UNCERTAIN, Observation.UNCERTAIN, Observation.UNCERTAIN)
    assert (await api.queue.complete(running, advisory, stopped=True)).result == advisory
    async with api.sessions() as session:
        assert await SqlMediaTransaction(session).current_photo(owner.id) == photo


async def test_catalogue_suggestion_is_bounded_selectable_and_never_auto_applied(
    ai_engine: AsyncEngine,
) -> None:
    from studymate.domain.ai.tasks import SubjectSuggestions, SuggestSubject
    from studymate.infrastructure.persistence.catalogue_models import SubjectRecord
    from studymate.infrastructure.persistence.goals import SqlGoalTransaction
    from tests.integration.catalogue_fixture import subject

    owner = await actor(ai_engine)
    api = services(ai_engine)
    source = await goal(ai_engine, owner)
    known = await subject(ai_engine)
    request = StudentSubmission(AiKind.SUGGEST_SUBJECT, source, candidate_ids=(known.id,))
    with pytest.raises(AiSourceUnavailableError):
        await api.submit(
            owner.credential, replace(request, candidate_ids=(uuid4(),)), IntentKey(str(uuid4()))
        )
    created = await api.submit(owner.credential, request, IntentKey(str(uuid4())))
    assert isinstance(created.task, SuggestSubject)
    running = await api.queue.claim()
    assert running is not None
    with pytest.raises(ValueError, match="conform"):
        await api.queue.complete(running, SubjectSuggestions((uuid4(),)), stopped=True)
    assert (
        await api.queue.complete(running, SubjectSuggestions((known.id,)), stopped=True)
    ).state == JobState.SUCCEEDED
    async with api.sessions() as session:
        saved = await SqlGoalTransaction(session).active_goal(owner.id)
    assert saved is not None
    assert isinstance(saved.goal.content.subject, CustomSubjectRef)
    async with api.sessions.begin() as session:
        await session.execute(update(SubjectRecord).values(archived_at=func.clock_timestamp()))
    with pytest.raises(AiSourceUnavailableError):
        await api.submit(owner.credential, request, IntentKey(str(uuid4())))
