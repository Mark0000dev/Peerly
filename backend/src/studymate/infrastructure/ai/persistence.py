import asyncio
import hmac
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.ai.drafts import draft_snapshot_source
from studymate.application.ai.policy import AdmissionPolicy
from studymate.application.ai.ports import (
    Admission,
    AiJobNotFoundError,
    AiQuotaError,
    AiSourceUnavailableError,
    AiUnavailableError,
    DraftSourceIntent,
    StudentSubmission,
)
from studymate.application.errors import StorageUnavailableError
from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.domain.ai.jobs import AiJob, Failure, JobState, Versions
from studymate.domain.ai.tasks import (
    AiKind,
    AiTask,
    AssessPhoto,
    Candidate,
    ClarifyGoal,
    SuggestSubject,
    kind_of,
)
from studymate.domain.media import MediaObjectKind, MediaObjectRef
from studymate.domain.study_context import CustomSubjectRef
from studymate.infrastructure.ai.codec import RESULT_CODEC, TASK_CODEC
from studymate.infrastructure.ai.models import (
    AiBudgetRecord,
    AiIntentRecord,
    AiJobRecord,
    AiSlotRecord,
)
from studymate.infrastructure.ai.runtime.availability import require_runtime_ready
from studymate.infrastructure.observability.origin import ExecutionOrigin
from studymate.infrastructure.observability.tracing import current_origin
from studymate.infrastructure.persistence.catalogue_models import SubjectRecord
from studymate.infrastructure.persistence.goals import SqlGoalTransaction
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.media_models import PhotoUploadRevisionRecord
from studymate.infrastructure.persistence.media_uploads import SqlMediaTransaction
from studymate.infrastructure.persistence.product_events import record_ai_terminal
from studymate.infrastructure.persistence.transactions import open_transaction


def job_value(record: AiJobRecord) -> AiJob:
    try:
        task = TASK_CODEC.validate_json(record.input_json)
        result = (
            RESULT_CODEC.validate_json(record.result_json)
            if record.result_json is not None
            else None
        )
    except ValidationError:
        raise RuntimeError("Stored AI snapshot does not conform") from None
    return AiJob(
        record.id,
        record.actor_id,
        task,
        record.digest,
        Versions(record.model, record.prompt, record.schema_version, record.adapter),
        record.created_at,
        record.deadline,
        record.not_before,
        JobState(record.state),
        record.attempts,
        record.generation,
        record.token,
        result,
        Failure(record.failure) if record.failure is not None else None,
    )


def save_state(record: AiJobRecord, value: AiJob) -> None:
    record.state = value.state.value
    record.attempts = value.attempts
    record.generation = value.generation
    record.token = value.token
    record.not_before = value.not_before
    record.result_json = (
        RESULT_CODEC.dump_json(value.result).decode() if value.result is not None else None
    )
    record.failure = value.failure.value if value.failure is not None else None


def job_origin(record: AiJobRecord) -> ExecutionOrigin | None:
    if record.request_id is None:
        return None
    return ExecutionOrigin(record.request_id, record.action_id, record.trace_id, record.span_id)


async def terminal_event(session: AsyncSession, record: AiJobRecord, at: datetime) -> None:
    await record_ai_terminal(session, job_value(record), at, job_origin(record))


async def lock_slot(session: AsyncSession) -> AiSlotRecord:
    # The migration seeds this row; ON CONFLICT also makes isolated test setup safe.
    await session.execute(
        insert(AiSlotRecord)
        .values(
            id=1,
            generation=0,
            sequence=0,
            interactive_streak=0,
        )
        .on_conflict_do_nothing()
    )
    return (
        await session.scalars(
            select(AiSlotRecord)
            .where(AiSlotRecord.id == 1)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).one()


@dataclass(frozen=True, slots=True)
class SqlAiTransaction(SqlIdentityTransaction):
    policy: AdmissionPolicy = field(default_factory=AdmissionPolicy)

    async def runtime_versions(self, at: datetime) -> Versions:
        del at  # Re-read DB clock after acquiring the bounded canonical lock.
        slot = await lock_slot(self.session)
        return require_runtime_ready(slot, await self.now())

    async def prepare(self, actor_id: UUID, submission: StudentSubmission) -> AiTask:
        if isinstance(submission.source, DraftSourceIntent):
            snapshot = draft_snapshot_source(submission)
            if submission.kind == AiKind.CLARIFY_GOAL and submission.text is not None:
                return ClarifyGoal(snapshot, submission.text, submission.target)
            if submission.kind == AiKind.SUGGEST_SUBJECT and submission.label is not None:
                return SuggestSubject(
                    snapshot, submission.label, await self._candidates(submission.candidate_ids)
                )
            raise AiSourceUnavailableError
        if submission.kind == AiKind.ASSESS_PHOTO:
            photo = await SqlMediaTransaction(self.session).current_photo(actor_id)
            if (
                photo is None
                or photo.upload_id != submission.source.id
                or photo.version != submission.source.version
            ):
                raise AiSourceUnavailableError
            revision = (
                await self.session.scalars(
                    select(PhotoUploadRevisionRecord)
                    .where(
                        PhotoUploadRevisionRecord.upload_id == photo.upload_id,
                        PhotoUploadRevisionRecord.account_id == actor_id,
                        PhotoUploadRevisionRecord.state == "ready",
                    )
                    .order_by(PhotoUploadRevisionRecord.version.desc())
                    .limit(1)
                )
            ).one_or_none()
            if revision is None or revision.attempt_id is None:
                raise AiSourceUnavailableError
            return AssessPhoto(
                submission.source,
                MediaObjectRef(photo.upload_id, MediaObjectKind.DISPLAY, revision.attempt_id),
            )
        saved = await SqlGoalTransaction(self.session).active_goal(actor_id)
        if (
            saved is None
            or saved.goal.id != submission.source.id
            or saved.goal.version != submission.source.version
        ):
            raise AiSourceUnavailableError
        if submission.kind == AiKind.CLARIFY_GOAL and submission.text is not None:
            return ClarifyGoal(submission.source, submission.text, submission.target)
        subject = saved.goal.content.subject
        if submission.kind != AiKind.SUGGEST_SUBJECT or not isinstance(subject, CustomSubjectRef):
            raise AiSourceUnavailableError
        return SuggestSubject(
            submission.source, subject.label, await self._candidates(submission.candidate_ids)
        )

    async def _candidates(self, candidate_ids: tuple[UUID, ...]) -> tuple[Candidate, ...]:
        rows = tuple(
            await self.session.scalars(
                select(SubjectRecord)
                .where(SubjectRecord.id.in_(candidate_ids), SubjectRecord.archived_at.is_(None))
                .order_by(SubjectRecord.id)
                .with_for_update(read=True)
            )
        )
        if len(rows) != len(candidate_ids):
            raise AiSourceUnavailableError
        return tuple(Candidate(row.id, row.name) for row in rows)

    async def replay(
        self, actor_id: UUID, kind: AiKind, key: IntentKey, digest: bytes
    ) -> AiJob | None:
        prior = await self.session.get(AiIntentRecord, (actor_id, kind.value, key.value))
        if prior is None:
            return None
        if not hmac.compare_digest(prior.digest, digest):
            raise IdempotencyConflictError
        return await self.owned(actor_id, prior.job_id)

    async def admit(self, intent: Admission, at: datetime) -> AiJob:
        actor_id, task, key, digest, versions = (
            intent.actor_id,
            intent.task,
            intent.key,
            intent.digest,
            intent.versions,
        )
        slot = await lock_slot(self.session)
        at = await self.now()
        require_runtime_ready(slot, at, versions)
        prior = await self.replay(actor_id, kind_of(task), key, digest)
        if prior is not None:
            return prior
        matching = (
            await self.session.scalars(
                select(AiJobRecord)
                .where(
                    AiJobRecord.actor_id == actor_id,
                    AiJobRecord.kind == kind_of(task).value,
                    AiJobRecord.digest == digest,
                    AiJobRecord.state.in_(("queued", "running")),
                    AiJobRecord.deadline > at,
                )
                .order_by(AiJobRecord.created_at)
                .limit(1)
            )
        ).one_or_none()
        if matching is not None:
            self.session.add(
                AiIntentRecord(
                    actor_id=actor_id,
                    kind=matching.kind,
                    key=key.value,
                    job_id=matching.id,
                    digest=digest,
                )
            )
            return job_value(matching)
        if slot.circuit is not None or (slot.paused_until is not None and slot.paused_until > at):
            raise AiUnavailableError
        expired = tuple(
            await self.session.scalars(
                update(AiJobRecord)
                .where(AiJobRecord.state == "queued", AiJobRecord.deadline <= at)
                .values(state="expired")
                .returning(AiJobRecord)
            )
        )
        for record in expired:
            await terminal_event(self.session, record, at)
        queued = (
            await self.session.scalars(
                select(func.count()).select_from(AiJobRecord).where(AiJobRecord.state == "queued")
            )
        ).one()
        interactive = (
            await self.session.scalars(
                select(func.count())
                .select_from(AiJobRecord)
                .where(
                    AiJobRecord.state == "queued", AiJobRecord.kind != AiKind.TRIAGE_REPORT.value
                )
            )
        ).one()
        internal = kind_of(task) == AiKind.TRIAGE_REPORT
        if queued >= self.policy.queue_limit or (
            not internal and interactive >= self.policy.queue_limit - self.policy.internal_reserve
        ):
            raise AiUnavailableError
        outstanding = (
            await self.session.scalars(
                select(func.count())
                .select_from(AiJobRecord)
                .where(
                    AiJobRecord.actor_id == actor_id, AiJobRecord.state.in_(("queued", "running"))
                )
            )
        ).one()
        if outstanding >= self.policy.student_outstanding:
            raise AiQuotaError
        budget = await self.session.get(AiBudgetRecord, actor_id)
        if budget is None:
            budget = AiBudgetRecord(
                actor_id=actor_id,
                tokens=float(self.policy.bucket_capacity),
                refilled_at=at,
                last_served=0,
            )
            self.session.add(budget)
        tokens = min(
            float(self.policy.bucket_capacity),
            budget.tokens
            + max(0.0, (at - budget.refilled_at).total_seconds()) / self.policy.refill_seconds,
        )
        if tokens < 1:
            raise AiQuotaError
        budget.tokens = tokens - 1
        budget.refilled_at = at
        record = AiJobRecord(
            id=uuid4(),
            actor_id=actor_id,
            kind=kind_of(task).value,
            source_id=task.source.id,
            source_version=task.source.version,
            digest=digest,
            input_json=TASK_CODEC.dump_json(task).decode(),
            model=versions.model,
            prompt=versions.prompt,
            schema_version=versions.schema,
            adapter=versions.adapter,
            state="queued",
            created_at=at,
            deadline=at
            + (self.policy.internal_lifetime if internal else self.policy.interactive_lifetime),
            not_before=at,
            attempts=0,
            generation=0,
        )
        origin = current_origin()
        if origin is not None:
            record.request_id = origin.request_id
            record.action_id = origin.action_id
            record.trace_id = origin.trace_id
            record.span_id = origin.span_id
        self.session.add(record)
        await self.session.flush()
        self.session.add(
            AiIntentRecord(
                actor_id=actor_id, kind=record.kind, key=key.value, job_id=record.id, digest=digest
            )
        )
        return job_value(record)

    async def owned(self, actor_id: UUID, job_id: UUID, *, cancel: bool = False) -> AiJob:
        # Slot before job, consistent with worker completion. Identity lock is already held.
        if cancel:
            await lock_slot(self.session)
        statement = select(AiJobRecord).where(
            AiJobRecord.id == job_id,
            AiJobRecord.actor_id == actor_id,
            AiJobRecord.kind != AiKind.TRIAGE_REPORT.value,
        )
        if cancel:
            statement = statement.with_for_update()
        record = (await self.session.scalars(statement)).one_or_none()
        if record is None:
            raise AiJobNotFoundError
        value = job_value(record)
        if cancel and value.pending:
            value = value.cancel()
            save_state(record, value)
            await terminal_event(self.session, record, await self.now())
        return value


@dataclass(frozen=True, slots=True)
class SqlAiUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    policy: AdmissionPolicy = field(default_factory=AdmissionPolicy)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlAiTransaction]:
        try:
            async with asyncio.timeout(self.policy.request_budget_seconds):
                async with open_transaction(self.sessions) as session:
                    yield SqlAiTransaction(session, self.policy)
        except (StorageUnavailableError, TimeoutError):
            raise AiUnavailableError from None


async def cancel_actor_jobs(session: AsyncSession, actor_id: UUID) -> None:
    """Lifecycle integration hook: caller already holds the account lock, same transaction.

    Retain business history and the occupied executor slot; heartbeat stops the child,
    or explicit physical-stop recovery follows a supervisor crash.
    """
    await lock_slot(session)
    at = await SqlAiTransaction(session).now()
    cancelled = tuple(
        await session.scalars(
            update(AiJobRecord)
            .where(AiJobRecord.actor_id == actor_id, AiJobRecord.state.in_(("queued", "running")))
            .values(state="cancelled")
            .returning(AiJobRecord)
        )
    )
    for record in cancelled:
        await terminal_event(session, record, at)
