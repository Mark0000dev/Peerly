"""Explicit canonical column mappings; never model __dict__, private bodies or guessed URLs."""

from uuid import UUID

from studymate.domain.ai.jobs import Failure, JobState
from studymate.domain.ai.tasks import AiKind
from studymate.domain.feedback.assessments import StudyAgain
from studymate.domain.feedback.outcomes import StudyAnswer
from studymate.domain.lifecycle.states import LifecycleOperation
from studymate.domain.messaging import MessageOutcome
from studymate.domain.operator.access import OperatorAccess
from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.operator.profile_media import (
    OperatorProfileMediaKind,
    OperatorProfileMediaRequest,
)
from studymate.domain.operator.timeline import (
    OperatorAuditDetail,
    OperatorEventFacts,
    OperatorEventKind,
    OperatorEventOrigin,
    OperatorEventSource,
    OperatorSourceKind,
    OperatorTimelineEvent,
)
from studymate.domain.profiles import OnboardingTask
from studymate.domain.requests.states import RequestState
from studymate.infrastructure.operator.models import (
    OperatorAccessRevisionRecord,
    OperatorAuditRecord,
)
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord


def required_id(value: UUID | None) -> UUID:
    if value is None:
        raise RuntimeError("Canonical operator projection lost its actual stored source identifier")
    return value


def profile_event_source(
    row: ProductEventRecord, kind: OperatorEventKind
) -> OperatorEventSource | None:
    owner = row.account_id
    source: OperatorEventSource | None = None
    if kind == OperatorEventKind.NOTIFICATION_PREFERENCE_CHANGED:
        source = OperatorEventSource(
            OperatorSourceKind.NOTIFICATION_PREFERENCE,
            owner,
            owner,
            version=row.notification_preference_version,
        )
    elif kind in {OperatorEventKind.SUPPORT_RECEIVED, OperatorEventKind.SUPPORT_STATUS_CHANGED}:
        source = OperatorEventSource(
            OperatorSourceKind.SUPPORT_CASE,
            required_id(row.support_case_id),
            owner,
            version=row.support_case_version,
        )
    elif kind in {OperatorEventKind.GOAL_SAVED, OperatorEventKind.GOAL_COMPLETED}:
        source = OperatorEventSource(
            OperatorSourceKind.GOAL, required_id(row.goal_id), owner, version=row.goal_version
        )
    elif kind in {OperatorEventKind.PROFILE_READY, OperatorEventKind.PROFILE_SAVED}:
        source = OperatorEventSource(
            OperatorSourceKind.PROFILE, owner, owner, version=row.profile_version
        )
    elif kind == OperatorEventKind.HELP_SAVED:
        source = OperatorEventSource(
            OperatorSourceKind.HELP, owner, owner, version=row.help_version
        )
    elif kind == OperatorEventKind.PHOTO_PUBLISHED:
        source = OperatorEventSource(
            OperatorSourceKind.PHOTO, owner, owner, version=row.photo_version
        )
    elif kind in {
        OperatorEventKind.PROFILE_HIDDEN,
        OperatorEventKind.PROFILE_RESTORED,
        OperatorEventKind.EXPOSURE_CONFIRMED,
    }:
        source = OperatorEventSource(
            OperatorSourceKind.VISIBILITY, owner, owner, version=row.visibility_version
        )
    elif kind == OperatorEventKind.EMAIL_CONFIRMED:
        source = OperatorEventSource(OperatorSourceKind.ACCOUNT, owner, owner)
    elif kind == OperatorEventKind.AI_COMPLETED:
        source = OperatorEventSource(OperatorSourceKind.AI_JOB, required_id(row.ai_job_id), owner)
    elif kind == OperatorEventKind.REPORT_CREATED:
        source = OperatorEventSource(
            OperatorSourceKind.PROFILE_REPORT, required_id(row.report_id), owner
        )
    elif kind == OperatorEventKind.BLOCK_CHANGED:
        source = OperatorEventSource(
            OperatorSourceKind.BLOCK,
            required_id(row.block_relationship_id),
            owner,
            version=row.block_version,
        )
    elif kind == OperatorEventKind.DECK_DECISION_CHANGED:
        source = OperatorEventSource(
            OperatorSourceKind.DECK_DECISION,
            required_id(row.private_pass_id),
            owner,
            version=row.private_pass_version,
        )
    return source


def contact_event_source(
    row: ProductEventRecord, kind: OperatorEventKind
) -> OperatorEventSource | None:
    owner = row.account_id
    source: OperatorEventSource | None = None
    if kind == OperatorEventKind.REQUEST_CHANGED:
        source = OperatorEventSource(
            OperatorSourceKind.REQUEST,
            required_id(row.connection_request_id),
            owner,
            version=row.connection_request_version,
            related_account_id=required_id(row.connection_request_recipient_id),
        )
    elif kind == OperatorEventKind.REQUEST_VIEWED:
        source = OperatorEventSource(
            OperatorSourceKind.REQUEST_VIEW, required_id(row.request_view_ack_id), owner
        )
    elif kind in {OperatorEventKind.MESSAGE_CONFIRMED, OperatorEventKind.MESSAGE_CANCELLED}:
        source = OperatorEventSource(
            OperatorSourceKind.MESSAGE_OPERATION, required_id(row.message_operation_id), owner
        )
    elif kind == OperatorEventKind.CONVERSATION_READ:
        source = OperatorEventSource(
            OperatorSourceKind.CONVERSATION_READ,
            required_id(row.conversation_read_id),
            owner,
            conversation_id=required_id(row.read_conversation_id),
        )
    elif kind == OperatorEventKind.GOAL_SHARED:
        source = OperatorEventSource(
            OperatorSourceKind.GOAL_SHARE,
            required_id(row.goal_share_id),
            owner,
            version=row.goal_share_context_version,
            conversation_id=required_id(row.goal_share_conversation_id),
        )
    return source


def journal_event_source(
    row: ProductEventRecord, kind: OperatorEventKind
) -> OperatorEventSource | None:
    owner = row.account_id
    source: OperatorEventSource | None = None
    if kind == OperatorEventKind.ACCOUNT_LIFECYCLE_CHANGED:
        source = OperatorEventSource(
            OperatorSourceKind.LIFECYCLE,
            required_id(row.lifecycle_revision_id),
            owner,
            version=row.lifecycle_version,
            related_account_id=required_id(row.lifecycle_account_id),
        )
    elif kind == OperatorEventKind.OPERATOR_INSPECTED:
        source = OperatorEventSource(
            OperatorSourceKind.OPERATOR_AUDIT,
            required_id(row.operator_audit_id),
            owner,
            operator_access_version=row.operator_access_version,
        )
    elif kind == OperatorEventKind.STUDY_REPORTED:
        source = OperatorEventSource(
            OperatorSourceKind.STUDY_OUTCOME,
            required_id(row.study_outcome_id),
            owner,
            version=row.study_outcome_version,
            conversation_id=required_id(row.study_conversation_id),
        )
    elif kind == OperatorEventKind.FEEDBACK_SAVED:
        source = OperatorEventSource(
            OperatorSourceKind.FEEDBACK,
            required_id(row.peer_feedback_id),
            owner,
            version=row.peer_feedback_version,
        )
    elif kind == OperatorEventKind.STUDY_PROMPT:
        source = OperatorEventSource(
            OperatorSourceKind.STUDY_PROMPT,
            required_id(row.study_prompt_id),
            owner,
            conversation_id=required_id(row.study_prompt_conversation_id),
        )
    return source


def event_value(row: ProductEventRecord) -> OperatorTimelineEvent:
    kind = OperatorEventKind(row.kind)
    source = (
        profile_event_source(row, kind)
        or contact_event_source(row, kind)
        or journal_event_source(row, kind)
    )
    if source is None:
        raise RuntimeError("Operator event projection has no supported actual canonical source")
    sources = (
        (source,)
        if row.subject_id is None
        else (source, OperatorEventSource(OperatorSourceKind.SUBJECT, row.subject_id, None))
    )
    facts = OperatorEventFacts(
        lifecycle_operation=LifecycleOperation(row.lifecycle_operation)
        if row.lifecycle_operation is not None
        else None,
        topic_present=row.topic_present,
        shared_learning=row.shared_learning,
        onboarding_task=OnboardingTask(row.onboarding_task)
        if row.onboarding_task is not None
        else None,
        ai_kind=AiKind(row.ai_kind) if row.ai_kind is not None else None,
        ai_state=JobState(row.ai_state) if row.ai_state is not None else None,
        ai_reason=Failure(row.ai_reason) if row.ai_reason is not None else None,
        blocked=row.blocked,
        passed=row.private_passed,
        request_state=RequestState(row.connection_request_state)
        if row.connection_request_state is not None
        else None,
        message_state=MessageOutcome(row.message_operation_state)
        if row.message_operation_state is not None
        else None,
        study_answer=StudyAnswer(row.study_answer) if row.study_answer is not None else None,
        feedback_again=StudyAgain(row.feedback_again) if row.feedback_again is not None else None,
        operator_action=OperatorAction(row.operator_action)
        if row.operator_action is not None
        else None,
    )
    return OperatorTimelineEvent(
        row.id,
        row.account_id,
        kind,
        row.schema_version,
        row.occurred_at,
        sources,
        facts,
        OperatorEventOrigin(row.request_id, row.action_id, row.trace_id, row.span_id),
        row.request_initiator_id,
    )


def audit_value(
    row: OperatorAuditRecord, grant: OperatorAccessRevisionRecord
) -> OperatorAuditDetail:
    action = OperatorAction(row.action)
    resource = OperatorResourceKind(row.resource_kind)
    result_kind = {
        OperatorAction.SEARCH_ACCOUNTS: OperatorResourceKind.ACCOUNT,
        OperatorAction.READ_ACCOUNT: OperatorResourceKind.ACCOUNT,
        OperatorAction.READ_CONVERSATION_MESSAGES: OperatorResourceKind.MESSAGE,
        OperatorAction.SEARCH_EVENTS: OperatorResourceKind.EVENT,
        OperatorAction.READ_EVENT: OperatorResourceKind.EVENT,
        OperatorAction.READ_AUDIT: OperatorResourceKind.AUDIT,
        OperatorAction.SEARCH_REPORTS: OperatorResourceKind.REPORT,
        OperatorAction.READ_REPORT: OperatorResourceKind.REPORT,
        OperatorAction.READ_MEDIA: OperatorResourceKind.PROFILE_MEDIA,
        OperatorAction.READ_SUPPORT_CASE: OperatorResourceKind.SUPPORT_CASE,
    }[action]
    if (
        row.operator_id != grant.account_id
        or row.operator_access_version != grant.version
        or not row.operator_access_active
        or not grant.active
    ):
        raise RuntimeError("Operator audit projection lost its actual historical active grant")
    media_request = None
    if row.requested_media_kind is not None:
        media_request = OperatorProfileMediaRequest(
            required_id(row.requested_media_owner_id),
            required_id(row.requested_id),
            required_id(row.requested_media_attempt_id),
            OperatorProfileMediaKind(row.requested_media_kind),
        )
    elif row.requested_media_owner_id is not None or row.requested_media_attempt_id is not None:
        raise RuntimeError("Media inspection lost its actual requested kind")
    audit = OperatorAudit(
        row.id,
        OperatorAccess(grant.account_id, grant.version, grant.active, grant.changed_at),
        action,
        OperatorResourceRef(resource, row.requested_id) if row.requested_id is not None else None,
        tuple(OperatorResourceRef(result_kind, source_id) for source_id in row.result_ids),
        row.occurred_at,
        OperatorAuditOutcome(row.outcome),
        row.query_fingerprint,
        media_request,
        row.actual_source_upload_id,
    )
    return OperatorAuditDetail(
        audit, OperatorEventOrigin(row.http_request_id, row.action_id, row.trace_id, row.span_id)
    )
