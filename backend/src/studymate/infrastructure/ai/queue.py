"""Short transactions; expired leases never release physical capacity."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.ai.ports import (
    AiSourceUnavailableError,
    DraftSourceIntent,
    StudentSubmission,
)
from studymate.domain.ai.jobs import AiJob, Failure, JobState, LeaseLostError
from studymate.domain.ai.tasks import (
    AiKind,
    AiResult,
    ClarifyGoal,
    DraftSnapshotSource,
    GoalTextTarget,
    SuggestSubject,
    TriageReport,
    kind_of,
)
from studymate.infrastructure.ai.models import (
    AiAttemptRecord,
    AiBudgetRecord,
    AiJobRecord,
    AiSlotRecord,
)
from studymate.infrastructure.ai.persistence import (
    SqlAiTransaction,
    job_value,
    lock_slot,
    save_state,
    terminal_event,
)
from studymate.infrastructure.ai.runtime.availability import require_runtime_ready
from studymate.infrastructure.observability.origin import ExecutionOrigin
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
)
from studymate.infrastructure.persistence.transactions import open_transaction

INTERACTIVE_WEIGHT = 4


class TrustedReportSource(Protocol):
    """Check report authority/evidence in the caller's existing queue transaction.

    Default locking precedes slot/job locks in claim and completion. Implementations
    must not open another session, transaction or connection; typed source failures
    must survive unchanged rather than being coerced to a boolean account check.
    """

    async def check(
        self, session: AsyncSession, job: AiJob, *, lock: bool = True
    ) -> Failure | None: ...


async def _account(session: AsyncSession, actor_id: UUID) -> bool:
    account = (
        await session.scalars(
            select(AccountRecord)
            .where(AccountRecord.id == actor_id)
            .with_for_update(key_share=True)
        )
    ).one()
    binding = await session.get(InstitutionalBindingRecord, actor_id)
    return (
        account.deleted_at is None
        and account.banned_at is None
        and binding is not None
        and binding.revoked_at is None
    )


async def _due(session: AsyncSession, at: datetime, streak: int) -> UUID | None:
    internal_due = (
        await session.scalars(
            select(AiJobRecord.id)
            .where(
                AiJobRecord.state == "queued",
                AiJobRecord.kind == AiKind.TRIAGE_REPORT.value,
                AiJobRecord.not_before <= at,
            )
            .limit(1)
        )
    ).one_or_none()
    prefer_internal = streak >= INTERACTIVE_WEIGHT and internal_due is not None
    return (
        await session.scalars(
            select(AiJobRecord.id)
            .join(
                AiBudgetRecord,
                AiBudgetRecord.actor_id == AiJobRecord.actor_id,
            )
            .where(AiJobRecord.state == "queued", AiJobRecord.not_before <= at)
            .order_by(
                case(
                    (AiJobRecord.kind == AiKind.TRIAGE_REPORT.value, 0 if prefer_internal else 1),
                    else_=1 if prefer_internal else 0,
                ),
                AiBudgetRecord.last_served,
                AiJobRecord.created_at,
                AiJobRecord.id,
            )
            .limit(1)
        )
    ).one_or_none()


def _oldest_age(at: datetime, oldest: datetime | None) -> float:
    return max(0.0, (at - oldest).total_seconds()) if oldest is not None else 0.0


def _fence(slot: AiSlotRecord, job: AiJob, at: datetime) -> None:
    if (
        slot.token != job.token
        or slot.generation != job.generation
        or slot.job_id != job.id
        or slot.lease_until is None
        or slot.lease_until <= at
    ):
        raise LeaseLostError


@dataclass(frozen=True, slots=True)
class AiQueueSnapshot:
    queued: int = 0
    oldest_seconds: float = 0.0
    occupied: bool = False
    circuit_open: bool = False


@dataclass(frozen=True, slots=True)
class SqlAiQueue:
    sessions: async_sessionmaker[AsyncSession]
    reports: TrustedReportSource | None = None
    worker_id: UUID | None = None

    async def snapshot(self) -> AiQueueSnapshot:
        async with open_transaction(self.sessions) as session:
            count, oldest = (
                await session.execute(
                    select(func.count(AiJobRecord.id), func.min(AiJobRecord.created_at)).where(
                        AiJobRecord.state == "queued"
                    )
                )
            ).one()
            slot = await session.get(AiSlotRecord, 1)
            at = await SqlAiTransaction(session).now()
            return AiQueueSnapshot(
                count,
                _oldest_age(at, oldest),
                slot is not None and slot.token is not None,
                slot is not None
                and (
                    slot.circuit is not None
                    or (slot.paused_until is not None and slot.paused_until > at)
                ),
            )

    async def origin(self, job_id: UUID) -> ExecutionOrigin | None:
        async with open_transaction(self.sessions) as session:
            record = await session.get(AiJobRecord, job_id)
            if record is None or record.request_id is None:
                return None
            return ExecutionOrigin(
                record.request_id, record.action_id, record.trace_id, record.span_id
            )

    async def _eligible(self, session: AsyncSession, job: AiJob) -> Failure | None:
        if isinstance(job.task, TriageReport):
            if self.reports is None:
                return Failure.ACCOUNT
            return await self.reports.check(session, job)
        if not await _account(session, job.actor_id):
            return Failure.ACCOUNT
        submission = StudentSubmission(
            kind_of(job.task),
            DraftSourceIntent(job.task.source.id, job.task.source.version)
            if isinstance(job.task.source, DraftSnapshotSource)
            else job.task.source,
            job.task.text if isinstance(job.task, ClarifyGoal) else None,
            tuple(candidate.id for candidate in job.task.candidates)
            if isinstance(job.task, SuggestSubject)
            else (),
            target=job.task.target if isinstance(job.task, ClarifyGoal) else GoalTextTarget.CONTEXT,
            label=job.task.label
            if isinstance(job.task, SuggestSubject)
            and isinstance(job.task.source, DraftSnapshotSource)
            else None,
        )
        try:
            prepared = await SqlAiTransaction(session).prepare(job.actor_id, submission)
            if prepared.source != job.task.source:
                return Failure.STALE_SOURCE
        except AiSourceUnavailableError:
            return Failure.STALE_SOURCE
        return None

    async def claim(self) -> AiJob | None:
        async with open_transaction(self.sessions) as session:
            transaction = SqlAiTransaction(session)
            at = await transaction.now()
            # Optimistic lookup prevents inversion with student account -> slot order.
            snapshot = await session.get(AiSlotRecord, 1)
            candidate = await _due(
                session, at, snapshot.interactive_streak if snapshot is not None else 0
            )
            if candidate is None:
                return None
            record = (
                await session.scalars(select(AiJobRecord).where(AiJobRecord.id == candidate))
            ).one()
            original = job_value(record)
            invalid = await self._eligible(session, original)
            slot = await lock_slot(session)
            at = await transaction.now()
            if self.worker_id is not None:
                require_runtime_ready(slot, at, original.versions, worker_id=self.worker_id)
            if (
                slot.token is not None
                or slot.circuit is not None
                or (slot.paused_until is not None and slot.paused_until > at)
            ):
                return None
            if await _due(session, at, slot.interactive_streak) != candidate:
                return None
            await session.refresh(record, with_for_update={"skip_locked": True})
            if record.state != "queued":
                return None
            claimed = job_value(record).claim(uuid4(), slot.generation + 1, at)
            if invalid is not None and claimed.state == JobState.RUNNING:
                claimed = claimed.fail(invalid, at, timedelta(0))
            save_state(record, claimed)
            if claimed.state != JobState.RUNNING:
                await terminal_event(session, record, at)
                return None
            slot.generation = claimed.generation
            slot.token = claimed.token
            slot.job_id = claimed.id
            slot.lease_until = at + timedelta(seconds=45)
            slot.sequence += 1
            slot.interactive_streak = (
                0
                if kind_of(claimed.task) == AiKind.TRIAGE_REPORT
                else min(INTERACTIVE_WEIGHT, slot.interactive_streak + 1)
            )
            budget = (
                await session.scalars(
                    select(AiBudgetRecord).where(AiBudgetRecord.actor_id == claimed.actor_id)
                )
            ).one()
            budget.last_served = slot.sequence
            session.add(
                AiAttemptRecord(
                    job_id=claimed.id,
                    number=claimed.attempts,
                    token=claimed.token,
                    generation=claimed.generation,
                    started_at=at,
                )
            )
            return claimed

    async def heartbeat(self, job: AiJob) -> bool:
        async with open_transaction(self.sessions) as session:
            slot = await lock_slot(session)
            at = await SqlAiTransaction(session).now()
            _fence(slot, job, at)
            record = (
                await session.scalars(select(AiJobRecord).where(AiJobRecord.id == job.id))
            ).one()
            if record.state != "running":
                return False
            slot.lease_until = at + timedelta(seconds=45)
            return True

    async def complete(
        self,
        job: AiJob,
        result: AiResult | Failure,
        *,
        stopped: bool,
        retry_after: timedelta = timedelta(seconds=2),
    ) -> AiJob:
        if not stopped:
            raise ValueError("Physical process termination must be confirmed before releasing slot")
        async with open_transaction(self.sessions) as session:
            invalid = await self._eligible(session, job)
            slot = await lock_slot(session)
            at = await SqlAiTransaction(session).now()
            _fence(slot, job, at)
            record = (
                await session.scalars(
                    select(AiJobRecord).where(AiJobRecord.id == job.id).with_for_update()
                )
            ).one()
            current = job_value(record)
            outcome: AiResult | Failure = invalid if invalid is not None else result
            value = (
                current.fail(outcome, at, retry_after)
                if isinstance(outcome, Failure)
                else current.finish(outcome, at)
            )
            save_state(record, value)
            if value != current and not value.pending:
                await terminal_event(session, record, at)
            await self._release(
                session,
                slot,
                job,
                at,
                value.failure.value if value.failure is not None else value.state.value,
            )
            if result == Failure.AUTH:
                slot.circuit = Failure.AUTH.value
            if result == Failure.RATE_LIMIT:
                slot.paused_until = at + retry_after
            return value

    async def recover_stopped(
        self, token: UUID, generation: int, *, stopped: bool, expected_worker: UUID | None = None
    ) -> None:
        """Runtime proves old group/container dead; never infer from a database lease."""
        if not stopped:
            raise ValueError("Uncertain physical termination keeps executor paused")
        async with open_transaction(self.sessions) as session:
            slot = await lock_slot(session)
            if expected_worker is not None and (
                slot.runtime_worker_id != expected_worker or slot.runtime_state != "blocked"
            ):
                raise LeaseLostError
            if slot.token != token or slot.generation != generation or slot.job_id is None:
                raise LeaseLostError
            at = await SqlAiTransaction(session).now()
            record = (
                await session.scalars(
                    select(AiJobRecord).where(AiJobRecord.id == slot.job_id).with_for_update()
                )
            ).one()
            original = job_value(record)
            value = original.fail(Failure.EXECUTOR_LOST, at, timedelta(seconds=2))
            save_state(record, value)
            if value != original and not value.pending:
                await terminal_event(session, record, at)
            await self._release(session, slot, original, at, Failure.EXECUTOR_LOST.value)

    async def _release(
        self, session: AsyncSession, slot: AiSlotRecord, job: AiJob, at: datetime, outcome: str
    ) -> None:
        attempt = (
            await session.scalars(
                select(AiAttemptRecord).where(
                    AiAttemptRecord.job_id == job.id, AiAttemptRecord.number == job.attempts
                )
            )
        ).one()
        attempt.ended_at = at
        attempt.outcome = outcome
        slot.token = None
        slot.job_id = None
        slot.lease_until = None
