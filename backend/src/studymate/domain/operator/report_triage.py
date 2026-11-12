"""Existing typed report AI output is advisory and never a moderation decision."""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID

from studymate.domain.ai.jobs import AiJob, Failure, JobState
from studymate.domain.ai.tasks import MAX_EVIDENCE, Priority, ReportTriage, Source, TriageReport
from studymate.domain.operator.access import OperatorAccess
from studymate.domain.operator.timeline import OperatorEventOrigin
from studymate.domain.report_moderation.reviews import ReviewReportSource
from studymate.domain.text import plain_text
from studymate.domain.time import require_aware

TRIAGE_SOURCE_TOKEN_LIFETIME = timedelta(minutes=5)
MAX_TRIAGE_SOURCE_VERSION = (1 << 31) - 1


@dataclass(frozen=True, slots=True)
class OperatorReportTriageObservation:
    report_id: UUID
    job_id: UUID
    source: Source
    state: JobState
    failure: Failure | None
    source_current: bool
    priority: Priority | None
    rationale: str | None = field(repr=False)


def observe_report_triage(
    report_id: UUID, job: AiJob, *, source_current: bool
) -> OperatorReportTriageObservation:
    if not isinstance(job.task, TriageReport):
        raise ValueError("Report triage requires the actual internal typed report task")
    result = job.result
    if result is not None and not isinstance(result, ReportTriage):
        raise ValueError("Report triage requires the actual typed advisory result")
    suggestion = result if source_current else None
    return OperatorReportTriageObservation(
        report_id,
        job.id,
        job.task.source,
        job.state,
        job.failure,
        source_current,
        suggestion.priority if suggestion is not None else None,
        suggestion.rationale if suggestion is not None else None,
    )


def triage_source_digest(report: ReviewReportSource, evidence: str) -> bytes:
    value = "\n".join(
        (
            "triage-evidence-v1",
            str(report.id),
            report.kind.value,
            str(report.reporter_id),
            str(report.target_id),
            str(report.context_id),
            evidence,
        )
    )
    return hashlib.sha256(value.encode("utf-8")).digest()


@dataclass(frozen=True, slots=True)
class ReportTriageEvidenceContext:
    report: ReviewReportSource
    review_version: int | None
    evidence: str = field(repr=False)

    def __post_init__(self) -> None:
        plain_text(self.evidence, minimum=1, maximum=MAX_EVIDENCE, multiline=True)
        if self.review_version is not None and (
            isinstance(self.review_version, bool) or self.review_version < 1
        ):
            raise ValueError("Triage context requires an actual review version or no review")

    @property
    def evidence_digest(self) -> bytes:
        return triage_source_digest(self.report, self.evidence)


@dataclass(frozen=True, slots=True)
class ReportTriageSourceClaims:
    report_id: UUID
    operator_id: UUID
    actor_session_id: UUID
    operator_access_version: int
    review_version: int | None
    evidence_digest: bytes = field(repr=False)
    issued_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.issued_at)
        require_aware(self.expires_at)
        if (
            not self.issued_at < self.expires_at <= self.issued_at + TRIAGE_SOURCE_TOKEN_LIFETIME
            or len(self.evidence_digest) != hashlib.sha256().digest_size
            or isinstance(self.operator_access_version, bool)
            or self.operator_access_version < 1
            or (
                self.review_version is not None
                and (isinstance(self.review_version, bool) or self.review_version < 1)
            )
        ):
            raise ValueError("Triage source requires bounded actual authority and evidence claims")


@dataclass(frozen=True, slots=True)
class ReportTriageEvidenceSnapshot:
    report: ReviewReportSource
    version: int
    previous_version: int | None
    review_version: int | None
    operator: OperatorAccess
    actor_session_id: UUID
    evidence: str = field(repr=False)
    evidence_digest: bytes = field(repr=False)
    captured_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.captured_at)
        if (
            isinstance(self.version, bool)
            or not 1 <= self.version <= MAX_TRIAGE_SOURCE_VERSION
            or self.previous_version != (self.version - 1 if self.version > 1 else None)
            or not self.operator.is_active(self.captured_at)
            or triage_source_digest(self.report, self.evidence) != self.evidence_digest
        ):
            raise ValueError("Triage snapshot requires actual consecutive immutable evidence proof")
        TriageReport(Source(self.report.id, self.version), self.evidence)

    @property
    def task(self) -> TriageReport:
        return TriageReport(Source(self.report.id, self.version), self.evidence)


@dataclass(frozen=True, slots=True)
class ReportTriageSubmission:
    job_id: UUID
    report_id: UUID
    source_version: int
    operator: OperatorAccess
    actor_session_id: UUID
    submitted_at: datetime
    event_id: UUID
    origin: OperatorEventOrigin = field(default_factory=OperatorEventOrigin)

    def __post_init__(self) -> None:
        require_aware(self.submitted_at)
        Source(self.report_id, self.source_version)
        if not self.operator.is_active(self.submitted_at):
            raise ValueError("Triage submission requires its original active operator grant")

    @property
    def occurrence_key(self) -> str:
        return f"triage-submitted:{self.job_id}"


@dataclass(frozen=True, slots=True)
class ReportTriageSourcePreview:
    report: ReviewReportSource
    context: ReportTriageEvidenceContext | None = field(repr=False)

    def __post_init__(self) -> None:
        if self.context is not None and self.context.report != self.report:
            raise ValueError("Triage preview context differs from its actual report source")
