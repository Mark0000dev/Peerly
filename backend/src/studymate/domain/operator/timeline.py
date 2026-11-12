"""Finite metadata from actual canonical sources; no private content/query bags."""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from studymate.domain.ai.jobs import Failure, JobState
from studymate.domain.ai.tasks import AiKind
from studymate.domain.feedback.assessments import StudyAgain
from studymate.domain.feedback.outcomes import StudyAnswer
from studymate.domain.lifecycle.states import LifecycleOperation
from studymate.domain.messaging import MessageOutcome
from studymate.domain.operator.audit import OperatorAction, OperatorAudit
from studymate.domain.profiles import OnboardingTask
from studymate.domain.requests.states import RequestState
from studymate.domain.time import require_aware

MAX_EVENT_SOURCE_REFS = 2


class OperatorEventKind(StrEnum):
    ACCOUNT_LIFECYCLE_CHANGED = "account.lifecycle_changed"
    GOAL_SAVED = "goal.saved"
    GOAL_COMPLETED = "goal.completed"
    PROFILE_SAVED = "profile.saved"
    HELP_SAVED = "help.saved"
    PHOTO_PUBLISHED = "photo.published"
    PROFILE_READY = "profile.ready"
    PROFILE_HIDDEN = "profile.hidden"
    PROFILE_RESTORED = "profile.restored"
    EMAIL_CONFIRMED = "auth.email_confirmed"
    AI_COMPLETED = "ai_job.completed"
    EXPOSURE_CONFIRMED = "discovery.exposure_confirmed"
    REPORT_CREATED = "report.created"
    REPORT_REVIEWED = "report.reviewed"
    REPORT_TRIAGE_SUBMITTED = "triage.submitted"
    PHOTO_REVIEWED = "photo.reviewed"
    BLOCK_CHANGED = "block.changed"
    DECK_DECISION_CHANGED = "discovery.pass_changed"
    REQUEST_CHANGED = "request.changed"
    REQUEST_VIEWED = "request.view_acknowledged"
    MESSAGE_CONFIRMED = "message.confirmed"
    MESSAGE_CANCELLED = "message.cancelled"
    CONVERSATION_READ = "conversation.read_acknowledged"
    GOAL_SHARED = "conversation.goal_shared"
    OPERATOR_INSPECTED = "operator.inspected"
    STUDY_REPORTED = "study.reported"
    FEEDBACK_SAVED = "feedback.saved"
    STUDY_PROMPT = "study.prompt_offered"
    NOTIFICATION_PREFERENCE_CHANGED = "notification_preference.changed"
    SUPPORT_RECEIVED = "support.received"
    SUPPORT_STATUS_CHANGED = "support.status_changed"


class OperatorSourceKind(StrEnum):
    LIFECYCLE = "account_lifecycle_revision"
    ACCOUNT = "account"
    PROFILE = "profile_revision"
    HELP = "help_revision"
    PHOTO = "photo_revision"
    VISIBILITY = "visibility_revision"
    GOAL = "goal_revision"
    SUBJECT = "subject"
    AI_JOB = "ai_job"
    PROFILE_REPORT = "profile_report"
    REPORT_REVIEW = "report_review_revision"
    REPORT_TRIAGE_SUBMISSION = "report_triage_submission"
    PHOTO_REVIEW = "photo_review_revision"
    BLOCK = "block_revision"
    DECK_DECISION = "private_pass_revision"
    REQUEST = "request_revision"
    REQUEST_VIEW = "request_view_ack"
    MESSAGE_OPERATION = "message_operation"
    CONVERSATION_READ = "conversation_read"
    GOAL_SHARE = "goal_share"
    OPERATOR_AUDIT = "operator_audit"
    STUDY_OUTCOME = "study_outcome"
    FEEDBACK = "feedback_revision"
    STUDY_PROMPT = "study_prompt"
    NOTIFICATION_PREFERENCE = "notification_preference_revision"
    SUPPORT_CASE = "support_case_revision"


VERSIONED_SOURCES = frozenset(
    {
        OperatorSourceKind.LIFECYCLE,
        OperatorSourceKind.REPORT_REVIEW,
        OperatorSourceKind.PHOTO_REVIEW,
        OperatorSourceKind.PROFILE,
        OperatorSourceKind.HELP,
        OperatorSourceKind.PHOTO,
        OperatorSourceKind.VISIBILITY,
        OperatorSourceKind.GOAL,
        OperatorSourceKind.BLOCK,
        OperatorSourceKind.DECK_DECISION,
        OperatorSourceKind.REQUEST,
        OperatorSourceKind.GOAL_SHARE,
        OperatorSourceKind.STUDY_OUTCOME,
        OperatorSourceKind.FEEDBACK,
        OperatorSourceKind.NOTIFICATION_PREFERENCE,
        OperatorSourceKind.SUPPORT_CASE,
    }
)
CONVERSATION_SOURCES = frozenset(
    {
        OperatorSourceKind.CONVERSATION_READ,
        OperatorSourceKind.GOAL_SHARE,
        OperatorSourceKind.STUDY_OUTCOME,
        OperatorSourceKind.STUDY_PROMPT,
    }
)


@dataclass(frozen=True, slots=True)
class OperatorEventSource:
    kind: OperatorSourceKind
    id: UUID
    owner_id: UUID | None
    version: int | None = None
    conversation_id: UUID | None = None
    related_account_id: UUID | None = None
    operator_access_version: int | None = None

    def __post_init__(self) -> None:
        if (self.owner_id is None) != (self.kind == OperatorSourceKind.SUBJECT):
            raise ValueError("Canonical source ownership differs from its actual resource kind")
        if (self.version is not None) != (self.kind in VERSIONED_SOURCES) or (
            self.version is not None and (isinstance(self.version, bool) or self.version < 1)
        ):
            raise ValueError("Canonical source requires its exact positive revision shape")
        if (self.conversation_id is not None) != (self.kind in CONVERSATION_SOURCES):
            raise ValueError(
                "Canonical source cannot invent or lose a stored conversation reference"
            )
        if (self.related_account_id is not None) != (
            self.kind in {OperatorSourceKind.REQUEST, OperatorSourceKind.LIFECYCLE}
        ) or (
            self.kind == OperatorSourceKind.REQUEST
            and self.related_account_id is not None
            and self.related_account_id == self.owner_id
        ):
            raise ValueError("Canonical source requires its actual recipient or lifecycle target")
        if (self.operator_access_version is not None) != (
            self.kind == OperatorSourceKind.OPERATOR_AUDIT
        ) or (
            self.operator_access_version is not None
            and (isinstance(self.operator_access_version, bool) or self.operator_access_version < 1)
        ):
            raise ValueError("Inspection source requires its actual operator grant revision")
        if (
            self.kind
            in {
                OperatorSourceKind.ACCOUNT,
                OperatorSourceKind.PROFILE,
                OperatorSourceKind.HELP,
                OperatorSourceKind.PHOTO,
                OperatorSourceKind.VISIBILITY,
                OperatorSourceKind.NOTIFICATION_PREFERENCE,
            }
            and self.id != self.owner_id
        ):
            raise ValueError("Account-keyed canonical source differs from its actual account")


@dataclass(frozen=True, slots=True)
class OperatorEventOrigin:
    http_request_id: UUID | None = None
    action_id: UUID | None = None
    trace_id: str | None = None
    span_id: str | None = None

    def __post_init__(self) -> None:
        if self.http_request_id is None and any(
            value is not None for value in (self.action_id, self.trace_id, self.span_id)
        ):
            raise ValueError("Canonical origin references require their actual HTTP request")
        if (self.trace_id is None) != (self.span_id is None):
            raise ValueError("Canonical origin requires a paired trace/span reference")
        if (
            self.trace_id is not None
            and self.span_id is not None
            and (
                re.fullmatch(r"[0-9a-f]{32}", self.trace_id) is None
                or self.trace_id == "0" * 32
                or re.fullmatch(r"[0-9a-f]{16}", self.span_id) is None
                or self.span_id == "0" * 16
            )
        ):
            raise ValueError("Canonical trace/span references must be valid nonzero identifiers")


@dataclass(frozen=True, slots=True)
class OperatorEventFacts:
    topic_present: bool | None = None
    shared_learning: bool | None = None
    onboarding_task: OnboardingTask | None = None
    ai_kind: AiKind | None = None
    ai_state: JobState | None = None
    ai_reason: Failure | None = None
    blocked: bool | None = None
    passed: bool | None = None
    request_state: RequestState | None = None
    message_state: MessageOutcome | None = None
    study_answer: StudyAnswer | None = None
    feedback_again: StudyAgain | None = None
    operator_action: OperatorAction | None = None
    lifecycle_operation: LifecycleOperation | None = None


EVENT_SOURCES = {
    OperatorEventKind.REPORT_TRIAGE_SUBMITTED: OperatorSourceKind.REPORT_TRIAGE_SUBMISSION,
    OperatorEventKind.REPORT_REVIEWED: OperatorSourceKind.REPORT_REVIEW,
    OperatorEventKind.PHOTO_REVIEWED: OperatorSourceKind.PHOTO_REVIEW,
    OperatorEventKind.ACCOUNT_LIFECYCLE_CHANGED: OperatorSourceKind.LIFECYCLE,
    OperatorEventKind.GOAL_SAVED: OperatorSourceKind.GOAL,
    OperatorEventKind.GOAL_COMPLETED: OperatorSourceKind.GOAL,
    OperatorEventKind.PROFILE_SAVED: OperatorSourceKind.PROFILE,
    OperatorEventKind.HELP_SAVED: OperatorSourceKind.HELP,
    OperatorEventKind.PHOTO_PUBLISHED: OperatorSourceKind.PHOTO,
    OperatorEventKind.PROFILE_READY: OperatorSourceKind.PROFILE,
    OperatorEventKind.PROFILE_HIDDEN: OperatorSourceKind.VISIBILITY,
    OperatorEventKind.PROFILE_RESTORED: OperatorSourceKind.VISIBILITY,
    OperatorEventKind.EMAIL_CONFIRMED: OperatorSourceKind.ACCOUNT,
    OperatorEventKind.AI_COMPLETED: OperatorSourceKind.AI_JOB,
    OperatorEventKind.EXPOSURE_CONFIRMED: OperatorSourceKind.VISIBILITY,
    OperatorEventKind.REPORT_CREATED: OperatorSourceKind.PROFILE_REPORT,
    OperatorEventKind.BLOCK_CHANGED: OperatorSourceKind.BLOCK,
    OperatorEventKind.DECK_DECISION_CHANGED: OperatorSourceKind.DECK_DECISION,
    OperatorEventKind.REQUEST_CHANGED: OperatorSourceKind.REQUEST,
    OperatorEventKind.REQUEST_VIEWED: OperatorSourceKind.REQUEST_VIEW,
    OperatorEventKind.MESSAGE_CONFIRMED: OperatorSourceKind.MESSAGE_OPERATION,
    OperatorEventKind.MESSAGE_CANCELLED: OperatorSourceKind.MESSAGE_OPERATION,
    OperatorEventKind.CONVERSATION_READ: OperatorSourceKind.CONVERSATION_READ,
    OperatorEventKind.GOAL_SHARED: OperatorSourceKind.GOAL_SHARE,
    OperatorEventKind.OPERATOR_INSPECTED: OperatorSourceKind.OPERATOR_AUDIT,
    OperatorEventKind.STUDY_REPORTED: OperatorSourceKind.STUDY_OUTCOME,
    OperatorEventKind.FEEDBACK_SAVED: OperatorSourceKind.FEEDBACK,
    OperatorEventKind.STUDY_PROMPT: OperatorSourceKind.STUDY_PROMPT,
    OperatorEventKind.NOTIFICATION_PREFERENCE_CHANGED: OperatorSourceKind.NOTIFICATION_PREFERENCE,
    OperatorEventKind.SUPPORT_RECEIVED: OperatorSourceKind.SUPPORT_CASE,
    OperatorEventKind.SUPPORT_STATUS_CHANGED: OperatorSourceKind.SUPPORT_CASE,
}


@dataclass(frozen=True, slots=True)
class OperatorTimelineEvent:
    id: UUID
    subject_account_id: UUID
    kind: OperatorEventKind
    schema_version: int
    occurred_at: datetime
    sources: tuple[OperatorEventSource, ...]
    facts: OperatorEventFacts
    origin: OperatorEventOrigin
    initiator_account_id: UUID | None = None

    def __post_init__(self) -> None:
        require_aware(self.occurred_at)
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise ValueError("Operator event requires the actual known schema version")
        if not 1 <= len(self.sources) <= MAX_EVENT_SOURCE_REFS or len(set(self.sources)) != len(
            self.sources
        ):
            raise ValueError("Operator event requires bounded distinct actual source references")
        first = self.sources[0]
        if first.kind != EVENT_SOURCES[self.kind] or first.owner_id != self.subject_account_id:
            raise ValueError("Operator event source differs from its actual subject/kind")
        if len(self.sources) > 1 and (
            self.sources[1].kind != OperatorSourceKind.SUBJECT
            or self.kind not in {OperatorEventKind.GOAL_SAVED, OperatorEventKind.GOAL_COMPLETED}
        ):
            raise ValueError("Operator event cannot invent extra canonical subject links")
        if self.initiator_account_id is not None and self.kind != OperatorEventKind.REQUEST_CHANGED:
            raise ValueError(
                "Only actual request transitions retain this distinct initiator source"
            )


@dataclass(frozen=True, slots=True)
class OperatorAuditDetail:
    audit: OperatorAudit
    origin: OperatorEventOrigin
