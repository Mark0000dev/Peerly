from uuid import UUID

from pydantic import AwareDatetime, Field

from studymate.application.operator.report_triage import (
    ReportTriageContextView,
    ReportTriageRead,
    ReportTriageView,
)
from studymate.domain.ai.jobs import Failure, JobState
from studymate.domain.ai.tasks import Priority
from studymate.domain.operator.profile_reports import OperatorReportKind
from studymate.presentation.operator.models import ClosedModel


class ReportTriageBody(ClosedModel):
    source_token: str = Field(min_length=1, max_length=1024, repr=False)


class ReportTriageContextResponse(ClosedModel):
    report_id: UUID
    kind: OperatorReportKind
    available: bool
    source_token: str | None = Field(repr=False)
    evidence: str | None = Field(repr=False)


class ReportTriageResponse(ClosedModel):
    report_id: UUID
    job_id: UUID
    source_version: int
    state: JobState
    failure: Failure | None
    source_current: bool
    priority: Priority | None
    rationale: str | None = Field(repr=False)
    operator_id: UUID
    operator_access_version: int
    actor_session_id: UUID
    submitted_at: AwareDatetime
    event_id: UUID
    http_request_id: UUID | None
    action_id: UUID | None
    trace_id: str | None
    span_id: str | None


class ReportTriageReadResponse(ClosedModel):
    report_id: UUID
    triage: ReportTriageResponse | None = Field(repr=False)


def triage_context_response(value: ReportTriageContextView) -> ReportTriageContextResponse:
    context = value.preview.context
    return ReportTriageContextResponse(
        report_id=value.preview.report.id,
        kind=value.preview.report.kind,
        available=context is not None,
        source_token=value.source_token,
        evidence=context.evidence if context is not None else None,
    )


def report_triage_response(value: ReportTriageView) -> ReportTriageResponse:
    observed, proof = value.observation, value.submission
    return ReportTriageResponse(
        report_id=observed.report_id,
        job_id=observed.job_id,
        source_version=observed.source.version,
        state=observed.state,
        failure=observed.failure,
        source_current=observed.source_current,
        priority=observed.priority,
        rationale=observed.rationale,
        operator_id=proof.operator.account_id,
        operator_access_version=proof.operator.version,
        actor_session_id=proof.actor_session_id,
        submitted_at=proof.submitted_at,
        event_id=proof.event_id,
        http_request_id=proof.origin.http_request_id,
        action_id=proof.origin.action_id,
        trace_id=proof.origin.trace_id,
        span_id=proof.origin.span_id,
    )


def report_triage_read_response(value: ReportTriageRead) -> ReportTriageReadResponse:
    return ReportTriageReadResponse(
        report_id=value.report_id,
        triage=report_triage_response(value.triage) if value.triage is not None else None,
    )
