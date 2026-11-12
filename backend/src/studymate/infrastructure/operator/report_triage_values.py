from studymate.domain.operator.access import OperatorAccess
from studymate.domain.operator.profile_reports import OperatorReportKind
from studymate.domain.operator.report_triage import (
    ReportTriageEvidenceSnapshot,
    ReportTriageSubmission,
)
from studymate.domain.operator.timeline import OperatorEventOrigin
from studymate.domain.report_moderation.reviews import ReviewReportSource
from studymate.infrastructure.operator.models import OperatorAccessRevisionRecord
from studymate.infrastructure.operator.report_triage_models import (
    ReportTriageEvidenceRecord,
    ReportTriageSubmissionRecord,
)


def triage_snapshot_value(
    row: ReportTriageEvidenceRecord, grant: OperatorAccessRevisionRecord
) -> ReportTriageEvidenceSnapshot:
    context_id = row.profile_context_id if row.report_kind == "profile" else row.message_context_id
    if context_id is None:
        raise RuntimeError("Triage snapshot lost its original discriminated evidence reference")
    report = ReviewReportSource(
        row.report_id,
        OperatorReportKind(row.report_kind),
        row.reporter_id,
        row.target_id,
        context_id,
    )
    return ReportTriageEvidenceSnapshot(
        report,
        row.version,
        row.previous_version,
        row.review_version,
        OperatorAccess(grant.account_id, grant.version, grant.active, grant.changed_at),
        row.actor_session_id,
        row.evidence,
        row.evidence_digest,
        row.captured_at,
    )


def triage_submission_value(
    row: ReportTriageSubmissionRecord, snapshot: ReportTriageEvidenceSnapshot
) -> ReportTriageSubmission:
    if (
        row.report_id,
        row.source_version,
        row.operator_id,
        row.operator_access_version,
        row.operator_access_active,
        row.actor_session_id,
    ) != (
        snapshot.report.id,
        snapshot.version,
        snapshot.operator.account_id,
        snapshot.operator.version,
        snapshot.operator.active,
        snapshot.actor_session_id,
    ):
        raise RuntimeError("Triage submission differs from its actual snapshot actor/session proof")
    return ReportTriageSubmission(
        row.job_id,
        row.report_id,
        row.source_version,
        snapshot.operator,
        row.actor_session_id,
        row.submitted_at,
        row.event_id,
        OperatorEventOrigin(row.http_request_id, row.action_id, row.trace_id, row.span_id),
    )
