from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import case, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.domain.ai.jobs import AiJob, JobState
from studymate.domain.ai.tasks import kind_of
from studymate.domain.discovery_freshness import ExposureConfirmation
from studymate.domain.discovery_passes import PrivatePassRevision
from studymate.domain.feedback.assessments import FeedbackRevision
from studymate.domain.feedback.outcomes import StudyOutcomeRevision, StudyPromptReceipt
from studymate.domain.goal_shares import GoalShare
from studymate.domain.lifecycle.states import BanRevision, BanTransition, DeletionTransition
from studymate.domain.media import PhotoRevision
from studymate.domain.message_reads import ConversationReadPosition
from studymate.domain.message_reports import MessageImageReport
from studymate.domain.messaging import MessageOperation
from studymate.domain.notification_preferences.state import NotificationPreference
from studymate.domain.onboarding import OnboardingActivation, ProfileLifecycle
from studymate.domain.operator.audit import OperatorAudit
from studymate.domain.operator.membership_verification import ManualMembershipVerification
from studymate.domain.operator.photo_review import PhotoReviewRevision
from studymate.domain.operator.report_triage import ReportTriageSubmission
from studymate.domain.profiles import ProfileRevision
from studymate.domain.relationships import BlockRevision
from studymate.domain.report_moderation.reviews import ReportReviewRevision
from studymate.domain.reports import ProfileReport
from studymate.domain.requests.states import ConnectionRequest, RequestState
from studymate.domain.requests.views import RequestViewReceipt
from studymate.domain.study_context import HelpRevision, StudyGoal
from studymate.domain.support.cases import SupportReceipt
from studymate.domain.time import require_aware
from studymate.infrastructure.ai.models import AiJobRecord
from studymate.infrastructure.changes.staging import stage_change_outbox
from studymate.infrastructure.lifecycle.models import LifecycleRevisionRecord
from studymate.infrastructure.notification_preferences.models import PreferenceRevisionRecord
from studymate.infrastructure.observability.origin import ExecutionOrigin
from studymate.infrastructure.observability.tracing import current_origin
from studymate.infrastructure.persistence.discovery_exposure import record_foreground_activity
from studymate.infrastructure.persistence.media_origin_models import MediaOriginRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.report_models import ProfileReportRecord
from studymate.infrastructure.support.models import SupportCaseRecord, SupportRevisionRecord


async def _append(
    session: AsyncSession,
    event: ProductEventRecord,
    *,
    foreground: bool = True,
    capture_origin: bool = True,
) -> None:
    origin = current_origin() if capture_origin else None
    if origin is not None:
        event.request_id = origin.request_id
        event.action_id = origin.action_id
        event.trace_id = origin.trace_id
        event.span_id = origin.span_id
    session.add(event)
    await session.flush()
    await stage_change_outbox(session, event)
    if foreground:
        await record_foreground_activity(session, event.account_id, event.occurred_at)


async def record_profile_saved(session: AsyncSession, revision: ProfileRevision) -> None:
    await _append(
        session,
        ProductEventRecord(
            id=uuid4(),
            account_id=revision.account_id,
            kind="profile.saved",
            occurrence_key=f"profile_revision:{revision.account_id}:{revision.version}",
            schema_version=1,
            occurred_at=revision.saved_at,
            profile_version=revision.version,
        ),
        foreground=False,
    )


async def record_help_saved(session: AsyncSession, revision: HelpRevision) -> None:
    await _append(
        session,
        ProductEventRecord(
            id=uuid4(),
            account_id=revision.account_id,
            kind="help.saved",
            occurrence_key=f"help_revision:{revision.account_id}:{revision.version}",
            schema_version=1,
            occurred_at=revision.saved_at,
            help_version=revision.version,
        ),
        foreground=False,
    )


async def record_photo_published(session: AsyncSession, revision: PhotoRevision) -> None:
    source = await session.get(MediaOriginRecord, (revision.upload_id, "queued"))
    await _append(
        session,
        ProductEventRecord(
            id=uuid4(),
            account_id=revision.account_id,
            kind="photo.published",
            occurrence_key=f"photo_revision:{revision.account_id}:{revision.version}",
            schema_version=1,
            occurred_at=revision.saved_at,
            photo_version=revision.version,
            request_id=source.request_id if source is not None else None,
            action_id=source.action_id if source is not None else None,
            trace_id=source.trace_id if source is not None else None,
            span_id=source.span_id if source is not None else None,
        ),
        foreground=False,
        capture_origin=False,
    )


async def record_goal_event(session: AsyncSession, goal: StudyGoal) -> None:
    await _append(
        session,
        ProductEventRecord(
            id=uuid4(),
            account_id=goal.account_id,
            kind="goal.saved" if goal.active else "goal.completed",
            occurrence_key=f"goal:{goal.id}:{goal.version}",
            schema_version=1,
            occurred_at=goal.updated_at,
            goal_id=goal.id,
            goal_version=goal.version,
            subject_id=goal.content.canonical_subject_id,
            topic_present=goal.content.topic is not None,
            shared_learning=goal.content.shared_learning,
        ),
    )


async def record_activation_event(session: AsyncSession, activation: OnboardingActivation) -> None:
    await _append(
        session,
        ProductEventRecord(
            id=uuid4(),
            account_id=activation.profile.account_id,
            kind="profile.ready",
            occurrence_key="activation",
            schema_version=1,
            occurred_at=activation.completed_at,
            profile_version=activation.profile.version,
            onboarding_task=activation.profile.task.value,
        ),
    )


async def record_visibility_event(session: AsyncSession, lifecycle: ProfileLifecycle) -> None:
    await _append(
        session,
        ProductEventRecord(
            id=uuid4(),
            account_id=lifecycle.account_id,
            kind="profile.hidden" if lifecycle.hidden else "profile.restored",
            occurrence_key=f"visibility:{lifecycle.visibility_version}",
            schema_version=1,
            occurred_at=lifecycle.changed_at,
            visibility_version=lifecycle.visibility_version,
        ),
    )


async def record_membership_event(session: AsyncSession, account_id: UUID, at: datetime) -> None:
    await _append(
        session,
        ProductEventRecord(
            id=uuid4(),
            account_id=account_id,
            kind="auth.email_confirmed",
            occurrence_key="institutional_binding",
            schema_version=1,
            occurred_at=at,
        ),
    )


async def record_manual_membership_event(
    session: AsyncSession,
    source: ManualMembershipVerification,
) -> None:
    """The exact operator mutation source, never consumed OTP or target foreground activity."""
    await _append(
        session,
        ProductEventRecord(
            id=source.event_id,
            account_id=source.account_id,
            kind="auth.email_confirmed",
            occurrence_key=source.occurrence_key,
            schema_version=1,
            occurred_at=source.verified_at,
        ),
        foreground=False,
    )


async def record_ai_terminal(
    session: AsyncSession,
    job: AiJob,
    at: datetime,
    origin: ExecutionOrigin | None,
) -> None:
    """Append once in the caller's transaction using the submitted job's origin."""
    require_aware(at)
    if job.pending or at < job.created_at:
        raise ValueError("Canonical AI outcome requires an actual terminal job")
    kind = kind_of(job.task).value
    reason = (
        job.failure.value
        if job.failure is not None and job.state in {JobState.FAILED, JobState.EXPIRED}
        else None
    )
    occurrence = f"ai:{job.id}:terminal"
    statement = (
        insert(ProductEventRecord)
        .values(
            id=uuid4(),
            account_id=job.actor_id,
            kind="ai_job.completed",
            occurrence_key=occurrence,
            schema_version=1,
            occurred_at=at,
            ai_job_id=job.id,
            ai_kind=kind,
            ai_state=job.state.value,
            ai_reason=reason,
            request_id=origin.request_id if origin is not None else None,
            action_id=origin.action_id if origin is not None else None,
            trace_id=origin.trace_id if origin is not None else None,
            span_id=origin.span_id if origin is not None else None,
        )
        .on_conflict_do_nothing(constraint="uq_product_events_occurrence")
        .returning(ProductEventRecord)
    )
    await session.flush()
    stored = (
        await session.execute(
            select(
                AiJobRecord.actor_id,
                AiJobRecord.kind,
                AiJobRecord.state,
                case(
                    (AiJobRecord.state.in_(("failed", "expired")), AiJobRecord.failure),
                    else_=None,
                ),
                AiJobRecord.source_id,
                AiJobRecord.source_version,
                AiJobRecord.request_id,
                AiJobRecord.action_id,
                AiJobRecord.trace_id,
                AiJobRecord.span_id,
            ).where(AiJobRecord.id == job.id)
        )
    ).one()
    expected_source = (
        job.actor_id,
        kind,
        job.state.value,
        reason,
        job.task.source.id,
        job.task.source.version,
        origin.request_id if origin is not None else None,
        origin.action_id if origin is not None else None,
        origin.trace_id if origin is not None else None,
        origin.span_id if origin is not None else None,
    )
    if tuple(stored) != expected_source:
        raise RuntimeError("Canonical AI outcome disagrees with its stored source")
    inserted = (await session.scalars(statement)).one_or_none()
    if inserted is not None:
        await stage_change_outbox(session, inserted)
        return
    prior = (
        await session.scalars(
            select(ProductEventRecord).where(
                ProductEventRecord.account_id == job.actor_id,
                ProductEventRecord.kind == "ai_job.completed",
                ProductEventRecord.occurrence_key == occurrence,
            )
        )
    ).one()
    actual = (
        prior.ai_job_id,
        prior.ai_kind,
        prior.ai_state,
        prior.ai_reason,
        prior.request_id,
        prior.action_id,
        prior.trace_id,
        prior.span_id,
    )
    expected = (
        job.id,
        kind,
        job.state.value,
        reason,
        origin.request_id if origin is not None else None,
        origin.action_id if origin is not None else None,
        origin.trace_id if origin is not None else None,
        origin.span_id if origin is not None else None,
    )
    if actual != expected:
        raise RuntimeError("Conflicting canonical AI terminal outcome")
    await stage_change_outbox(session, prior)


async def record_exposure_confirmation_event(
    session: AsyncSession,
    confirmation: ExposureConfirmation,
    visibility_version: int,
) -> None:
    instant = confirmation.confirmed_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    await _append(
        session,
        ProductEventRecord(
            id=uuid4(),
            account_id=confirmation.account_id,
            kind="discovery.exposure_confirmed",
            occurrence_key=f"exposure:{instant}",
            schema_version=1,
            occurred_at=confirmation.confirmed_at,
            visibility_version=visibility_version,
        ),
    )


async def record_profile_report_event(session: AsyncSession, report: ProfileReport) -> None:
    await _append(
        session,
        ProductEventRecord(
            id=uuid4(),
            account_id=report.reporter_id,
            kind="report.created",
            occurrence_key=f"report:{report.id}",
            schema_version=1,
            occurred_at=report.submitted_at,
            report_id=report.id,
        ),
    )


async def record_message_report_event(session: AsyncSession, report: MessageImageReport) -> None:
    source = await session.get(ProfileReportRecord, report.id)
    if (
        source is None
        or source.kind != "message_image"
        or source.reporter_id != report.reporter_id
        or source.context_id is not None
        or source.message_context_id != report.context.id
        or source.category != report.category.value
        or source.comment != report.comment
        or source.submitted_at != report.submitted_at
    ):
        raise ValueError("Canonical report must reference its actual retained image report source")
    await _append(
        session,
        ProductEventRecord(
            id=uuid4(),
            account_id=source.reporter_id,
            kind="report.created",
            occurrence_key=f"report:{source.id}",
            schema_version=1,
            occurred_at=source.submitted_at,
            report_id=source.id,
        ),
    )


async def record_block_event(session: AsyncSession, revision: BlockRevision) -> None:
    await _append(
        session,
        ProductEventRecord(
            id=uuid4(),
            account_id=revision.blocker_id,
            kind="block.changed",
            occurrence_key=f"block:{revision.relationship_id}:{revision.version}",
            schema_version=1,
            occurred_at=revision.changed_at,
            block_relationship_id=revision.relationship_id,
            block_version=revision.version,
            blocked=revision.blocked,
        ),
    )


async def record_private_pass_event(session: AsyncSession, revision: PrivatePassRevision) -> None:
    await _append(
        session,
        ProductEventRecord(
            id=uuid4(),
            account_id=revision.context.account_id,
            kind="discovery.pass_changed",
            occurrence_key=f"private-pass:{revision.id}:{revision.version}",
            schema_version=1,
            occurred_at=revision.changed_at,
            private_pass_id=revision.id,
            private_pass_version=revision.version,
            private_passed=revision.passed,
        ),
    )


async def record_request_outcome(
    session: AsyncSession, request: ConnectionRequest, initiator_id: UUID | None
) -> None:
    if initiator_id is not None and initiator_id not in (request.pair.low, request.pair.high):
        raise ValueError("Human request initiator must be an actual participant")
    await _append(
        session,
        ProductEventRecord(
            id=uuid4(),
            account_id=request.context.sender_id,
            kind="request.changed",
            occurrence_key=f"connection-request:{request.id}:{request.version}",
            schema_version=1,
            occurred_at=request.changed_at,
            connection_request_id=request.id,
            connection_request_version=request.version,
            connection_request_state=request.state.value,
            connection_request_recipient_id=request.context.recipient_id,
            request_initiator_id=initiator_id,
        ),
        foreground=False,
    )
    # Unavailable is a derived lifecycle consequence. Its actual hide/block
    # action already owns foreground activity and its original logical time.
    if initiator_id is not None and request.state != RequestState.UNAVAILABLE:
        await record_foreground_activity(session, initiator_id, request.changed_at)


async def record_request_viewed(session: AsyncSession, receipt: RequestViewReceipt) -> None:
    await _append(
        session,
        ProductEventRecord(
            id=uuid4(),
            account_id=receipt.viewer_id,
            kind="request.view_acknowledged",
            occurrence_key=f"request-view:{receipt.id}",
            schema_version=1,
            occurred_at=receipt.acknowledged_at,
            request_view_ack_id=receipt.id,
        ),
    )


async def record_message_outcome(session: AsyncSession, operation: MessageOperation) -> None:
    at = operation.message.sent_at if operation.message is not None else operation.cancelled_at
    if at is None:
        raise RuntimeError("Terminal message outcome lacks its actual source time")
    await _append(
        session,
        ProductEventRecord(
            id=uuid4(),
            account_id=operation.author_id,
            kind=f"message.{operation.outcome.value}",
            occurrence_key=f"message:{operation.id}",
            schema_version=1,
            occurred_at=at,
            message_operation_id=operation.id,
            message_operation_state=operation.outcome.value,
        ),
    )


async def record_conversation_read(
    session: AsyncSession, position: ConversationReadPosition
) -> None:
    await _append(
        session,
        ProductEventRecord(
            id=uuid4(),
            account_id=position.account_id,
            kind="conversation.read_acknowledged",
            occurrence_key=f"conversation-read:{position.id}",
            schema_version=1,
            occurred_at=position.acknowledged_at,
            conversation_read_id=position.id,
            read_conversation_id=position.conversation_id,
        ),
    )


async def record_conversation_goal_share(session: AsyncSession, share: GoalShare) -> None:
    await _append(
        session,
        ProductEventRecord(
            id=uuid4(),
            account_id=share.owner_id,
            kind="conversation.goal_shared",
            occurrence_key=f"conversation-goal:{share.id}",
            schema_version=1,
            occurred_at=share.shared_at,
            goal_share_id=share.id,
            goal_share_conversation_id=share.conversation_id,
            goal_share_context_version=share.context_version,
        ),
    )


async def record_operator_audit(session: AsyncSession, audit: OperatorAudit) -> None:
    await _append(
        session,
        ProductEventRecord(
            id=uuid4(),
            account_id=audit.access.account_id,
            kind="operator.inspected",
            occurrence_key=f"operator-audit:{audit.id}",
            schema_version=1,
            occurred_at=audit.at,
            operator_audit_id=audit.id,
            operator_access_version=audit.access.version,
            operator_action=audit.action.value,
        ),
        foreground=False,
    )


async def record_study_outcome(session: AsyncSession, revision: StudyOutcomeRevision) -> None:
    await _append(
        session,
        ProductEventRecord(
            id=uuid4(),
            account_id=revision.actor_id,
            kind="study.reported",
            occurrence_key=f"study-outcome:{revision.id}",
            schema_version=1,
            occurred_at=revision.changed_at,
            study_outcome_id=revision.id,
            study_conversation_id=revision.conversation_id,
            study_outcome_version=revision.version,
            study_answer=revision.answer.value,
        ),
    )


async def record_peer_feedback(session: AsyncSession, revision: FeedbackRevision) -> None:
    await _append(
        session,
        ProductEventRecord(
            id=uuid4(),
            account_id=revision.reviewer_id,
            kind="feedback.saved",
            occurrence_key=f"feedback:{revision.id}:{revision.version}",
            schema_version=1,
            occurred_at=revision.changed_at,
            peer_feedback_id=revision.id,
            peer_feedback_version=revision.version,
            feedback_again=revision.content.again.value,
        ),
    )


async def record_study_prompt(session: AsyncSession, receipt: StudyPromptReceipt) -> None:
    await _append(
        session,
        ProductEventRecord(
            id=uuid4(),
            account_id=receipt.actor_id,
            kind="study.prompt_offered",
            occurrence_key=f"study-prompt:{receipt.id}",
            schema_version=1,
            occurred_at=receipt.offered_at,
            study_prompt_id=receipt.id,
            study_prompt_conversation_id=receipt.conversation_id,
        ),
    )


async def record_account_lifecycle(
    session: AsyncSession, transition: BanTransition | DeletionTransition
) -> None:
    source = transition.revision
    if source is None:
        raise ValueError("A no-op has no new canonical lifecycle source")
    stored = await session.get(LifecycleRevisionRecord, source.id)
    if isinstance(source, BanRevision):
        actor, at = source.operator_access.account_id, source.changed_at
    else:
        actor, at = source.account_id, source.deleted_at
    if stored is None or (
        stored.account_id,
        stored.actor_id,
        stored.actor_session_id,
        stored.version,
        stored.operation,
        stored.changed_at,
        stored.after_banned_at,
        stored.after_deleted_at,
    ) != (
        source.account_id,
        actor,
        source.actor_session_id,
        source.version,
        source.operation.value,
        at,
        transition.after.banned_at,
        transition.after.deleted_at,
    ):
        raise RuntimeError("Canonical lifecycle source differs from the actual retained transition")
    await _append(
        session,
        ProductEventRecord(
            id=uuid4(),
            account_id=actor,
            kind="account.lifecycle_changed",
            occurrence_key=f"account-lifecycle:{source.id}",
            schema_version=1,
            occurred_at=stored.changed_at,
            lifecycle_revision_id=stored.id,
            lifecycle_account_id=stored.account_id,
            lifecycle_version=stored.version,
            lifecycle_operation=stored.operation,
            request_id=stored.http_request_id,
            action_id=stored.action_id,
            trace_id=stored.trace_id,
            span_id=stored.span_id,
        ),
        foreground=False,
        capture_origin=False,
    )


async def record_notification_preference_event(
    session: AsyncSession, account_id: UUID, result: NotificationPreference
) -> None:
    source = await session.get(PreferenceRevisionRecord, (account_id, result.version))
    if (
        source is None
        or result.changed_at is None
        or source.mode != result.mode.value
        or source.changed_at != result.changed_at
    ):
        raise RuntimeError("Preference event requires its actual immutable owner revision")
    await _append(
        session,
        ProductEventRecord(
            id=uuid4(),
            account_id=account_id,
            kind="notification_preference.changed",
            occurrence_key=f"notification-preference:{account_id}:{result.version}",
            schema_version=1,
            occurred_at=result.changed_at,
            notification_preference_version=result.version,
        ),
        foreground=False,
    )


async def record_support_event(
    session: AsyncSession, actor_id: UUID | None, receipt: SupportReceipt
) -> None:
    case = await session.get(SupportCaseRecord, receipt.case_id)
    revision = await session.get(SupportRevisionRecord, (receipt.case_id, receipt.version))
    if (
        case is None
        or revision is None
        or case.received_at != receipt.received_at
        or revision.changed_at != receipt.changed_at
        or revision.status != receipt.status.value
        or actor_id != (case.actor_id if receipt.version == 1 else revision.changed_by_id)
    ):
        raise RuntimeError("Support event requires its actual retained actor/source revision")
    if receipt.version == 1 and case.http_request_id is None:
        origin = current_origin()
        if origin is not None:
            case.http_request_id = origin.request_id
            case.action_id = origin.action_id
            case.trace_id = origin.trace_id
            case.span_id = origin.span_id
        await session.flush()
    if actor_id is None:
        # Anonymous case/revision is the real retained source, not a fictitious account event.
        return
    await _append(
        session,
        ProductEventRecord(
            id=uuid4(),
            account_id=actor_id,
            kind="support.received" if receipt.version == 1 else "support.status_changed",
            occurrence_key=f"support:{receipt.case_id}:{receipt.version}",
            schema_version=1,
            occurred_at=receipt.changed_at,
            support_case_id=receipt.case_id,
            support_case_version=receipt.version,
        ),
        foreground=False,
    )


async def record_report_review_event(session: AsyncSession, source: ReportReviewRevision) -> None:
    """Canonical human decision only; private reason stays in its business source.

    Main0059 metadata/DDL integration must precede mounting this new producer.
    The original operator, event ID/time and correlation are durable source facts,
    not the later caller/reader's foreground activity or ambient trace.
    """
    await _append(
        session,
        ProductEventRecord(
            id=source.event_id,
            account_id=source.operator.account_id,
            kind="report.reviewed",
            schema_version=1,
            occurrence_key=source.occurrence_key,
            occurred_at=source.reviewed_at,
            report_review_report_id=source.report_id,
            report_review_id=source.id,
            report_review_version=source.version,
            report_review_action=source.action.value,
            request_id=source.origin.http_request_id,
            action_id=source.origin.action_id,
            trace_id=source.origin.trace_id,
            span_id=source.origin.span_id,
        ),
        foreground=False,
        capture_origin=False,
    )


async def record_photo_review_event(session: AsyncSession, source: PhotoReviewRevision) -> None:
    """0059 human source only; no private reason or target foreground activity."""
    await _append(
        session,
        ProductEventRecord(
            id=source.id,
            account_id=source.operator_id,
            kind="photo.reviewed",
            schema_version=1,
            occurrence_key=f"photo-review:{source.id}",
            occurred_at=source.decided_at,
            photo_review_id=source.id,
            photo_review_version=source.version,
            photo_review_action=source.action.value,
            request_id=source.origin.http_request_id,
            action_id=source.origin.action_id,
            trace_id=source.origin.trace_id,
            span_id=source.origin.span_id,
        ),
        foreground=False,
        capture_origin=False,
    )


async def record_report_triage_submission(
    session: AsyncSession, source: ReportTriageSubmission
) -> None:
    """0060 producer, unmounted until source/job/canonical metadata is integrated.

    Advisory job admission is an actual privileged mutation, never an inspection,
    student foreground activity, automatic report decision or evidence-content log.
    """
    await _append(
        session,
        ProductEventRecord(
            id=source.event_id,
            account_id=source.operator.account_id,
            kind="triage.submitted",
            schema_version=1,
            occurrence_key=source.occurrence_key,
            occurred_at=source.submitted_at,
            triage_job_id=source.job_id,
            triage_report_id=source.report_id,
            triage_source_version=source.source_version,
            request_id=source.origin.http_request_id,
            action_id=source.origin.action_id,
            trace_id=source.origin.trace_id,
            span_id=source.origin.span_id,
        ),
        foreground=False,
        capture_origin=False,
    )
