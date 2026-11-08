"""Explicit bounded signals; never serialize tasks, results or exception details."""

import asyncio
from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import perf_counter

from opentelemetry import context, trace
from opentelemetry.context import Context
from opentelemetry.metrics import CallbackOptions, Counter, Histogram, Meter, Observation
from opentelemetry.trace import Link, Span, SpanContext, SpanKind, StatusCode, TraceFlags, Tracer

from studymate.application.ai.ports import AiQuotaError, AiUnavailableError, StudentSubmission
from studymate.application.ai.student import SubmitStudentJob
from studymate.application.errors import StorageUnavailableError
from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import SessionCredential
from studymate.domain.ai.jobs import AiJob, Failure, LeaseLostError
from studymate.domain.ai.tasks import AiKind, AiResult, kind_of
from studymate.infrastructure.ai.process import TerminationUncertainError
from studymate.infrastructure.ai.queue import AiQueueSnapshot, SqlAiQueue
from studymate.infrastructure.observability.origin import ExecutionOrigin


@dataclass(slots=True)
class AiObservation:
    tracer: Tracer | None
    attempts: Counter | None
    duration: Histogram | None
    wait: Histogram | None
    job: AiJob | None = None
    span: Span | None = None
    token: Token[Context] | None = None
    outcome: str = "unexpected_error"
    reason: Failure | None = None

    def claimed(self, job: AiJob, origin: ExecutionOrigin | None) -> None:
        self.job = job
        if self.wait is not None:
            self.wait.record(
                max(0.0, (datetime.now(UTC) - job.created_at).total_seconds()),
                {"kind": kind_of(job.task).value},
            )
        if self.tracer is None:
            return
        attributes: dict[str, str | int] = {
            "ai.job.id": str(job.id),
            "user.id": str(job.actor_id),
            "ai.kind": kind_of(job.task).value,
            "ai.source.id": str(job.task.source.id),
            "ai.source.version": job.task.source.version,
            "ai.generation": job.generation,
            "ai.attempt": job.attempts,
            "ai.model": job.versions.model,
            "ai.prompt.version": job.versions.prompt,
            "ai.schema.version": job.versions.schema,
        }
        links: list[Link] = []
        if origin is not None:
            attributes["origin.request.id"] = str(origin.request_id)
            if origin.action_id is not None:
                attributes["action.id"] = str(origin.action_id)
            if origin.trace_id is not None and origin.span_id is not None:
                links.append(
                    Link(
                        SpanContext(
                            int(origin.trace_id, 16),
                            int(origin.span_id, 16),
                            True,
                            TraceFlags(TraceFlags.SAMPLED),
                        )
                    )
                )
        self.span = self.tracer.start_span(
            "ai.execute",
            context=Context(),
            kind=SpanKind.CONSUMER,
            attributes=attributes,
            links=links,
        )
        self.token = context.attach(trace.set_span_in_context(self.span, Context()))

    def finish(self, seconds: float) -> None:
        try:
            if self.job is not None:
                dimensions = {"kind": kind_of(self.job.task).value, "outcome": self.outcome}
                if self.reason is not None:
                    dimensions["reason"] = self.reason.value
                if self.attempts is not None:
                    self.attempts.add(1, dimensions)
                if self.duration is not None:
                    self.duration.record(seconds, dimensions)
            if self.span is not None:
                self.span.set_attribute("ai.outcome", self.outcome)
                if self.outcome != "succeeded":
                    self.span.set_status(StatusCode.ERROR)
                self.span.end()
        finally:
            if self.token is not None:
                context.detach(self.token)


_ACTIVE: ContextVar[AiObservation | None] = ContextVar("ai_execution", default=None)


@dataclass(frozen=True, slots=True)
class ObservedAiQueue:
    queue: SqlAiQueue

    async def claim(self) -> AiJob | None:
        job = await self.queue.claim()
        observation = _ACTIVE.get()
        if job is not None and observation is not None:
            observation.claimed(job, await self.queue.origin(job.id))
        return job

    async def heartbeat(self, job: AiJob) -> bool:
        return await self.queue.heartbeat(job)

    async def complete(
        self,
        job: AiJob,
        result: AiResult | Failure,
        *,
        stopped: bool,
        retry_after: timedelta = timedelta(seconds=2),
    ) -> AiJob:
        completed = await self.queue.complete(job, result, stopped=stopped, retry_after=retry_after)
        observation = _ACTIVE.get()
        if observation is not None:
            observation.outcome = completed.state.value
            if completed.state.value not in {"succeeded", "cancelled"}:
                observation.reason = completed.failure
        return completed


class ObservedAiStep:
    def __init__(
        self,
        step: Callable[[], Awaitable[bool]],
        tracer: Tracer | None = None,
        meter: Meter | None = None,
    ) -> None:
        self.step = step
        self.tracer = tracer
        self.attempts = meter.create_counter("worker.ai.attempts") if meter is not None else None
        self.duration = (
            meter.create_histogram("worker.ai.execution.duration", unit="s")
            if meter is not None
            else None
        )
        self.wait = (
            meter.create_histogram("worker.ai.wait.duration", unit="s")
            if meter is not None
            else None
        )

    async def __call__(self) -> bool:
        observation = AiObservation(self.tracer, self.attempts, self.duration, self.wait)
        token = _ACTIVE.set(observation)
        started = perf_counter()
        try:
            result = await self.step()
            if not result:
                observation.outcome = "idle"
            return result
        except asyncio.CancelledError:
            observation.outcome = "supervisor_cancelled"
            raise
        except StorageUnavailableError:
            observation.outcome = "storage_unavailable"
            raise
        except LeaseLostError:
            observation.outcome = "lease_lost"
            raise
        except TerminationUncertainError:
            observation.outcome = "termination_uncertain"
            raise
        finally:
            try:
                observation.finish(perf_counter() - started)
            finally:
                _ACTIVE.reset(token)


@dataclass(frozen=True, slots=True)
class AiAdmissionSignals:
    accepted: Counter
    rejected: Counter

    def success(self, kind: AiKind) -> None:
        self.accepted.add(1, {"kind": kind.value})

    def reject(self, kind: AiKind, error: AiQuotaError | AiUnavailableError) -> None:
        self.rejected.add(
            1,
            {
                "kind": kind.value,
                "reason": "actor_quota"
                if isinstance(error, AiQuotaError)
                else "capacity_or_circuit",
            },
        )


@dataclass(frozen=True, slots=True)
class ObservedStudentSubmission:
    submit: SubmitStudentJob
    signals: AiAdmissionSignals

    async def __call__(
        self, credential: SessionCredential, submission: StudentSubmission, key: IntentKey
    ) -> AiJob:
        try:
            result = await self.submit(credential, submission, key)
        except (AiQuotaError, AiUnavailableError) as error:
            self.signals.reject(submission.kind, error)
            raise
        # This observes accepted submission responses (including replays), not unique jobs.
        self.signals.success(submission.kind)
        return result


class AiQueueSignals:
    """The runtime samples asynchronously; SDK callbacks only read immutable cached numbers."""

    def __init__(self, meter: Meter) -> None:
        self.latest = AiQueueSnapshot()
        meter.create_observable_gauge("worker.ai.queue.depth", callbacks=[self.depth])
        meter.create_observable_gauge("worker.ai.queue.oldest", callbacks=[self.oldest], unit="s")
        meter.create_observable_gauge("worker.ai.slot.occupied", callbacks=[self.occupied])
        meter.create_observable_gauge("worker.ai.circuit.open", callbacks=[self.circuit])

    async def sample(self, queue: SqlAiQueue) -> None:
        self.latest = await queue.snapshot()

    def depth(self, options: CallbackOptions) -> tuple[Observation]:
        del options
        return (Observation(self.latest.queued),)

    def oldest(self, options: CallbackOptions) -> tuple[Observation]:
        del options
        return (Observation(self.latest.oldest_seconds),)

    def occupied(self, options: CallbackOptions) -> tuple[Observation]:
        del options
        return (Observation(int(self.latest.occupied)),)

    def circuit(self, options: CallbackOptions) -> tuple[Observation]:
        del options
        return (Observation(int(self.latest.circuit_open)),)
