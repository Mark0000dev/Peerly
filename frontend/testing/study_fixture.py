"""Finite retained accepted-pair sources; actual outcome/feedback commands and live sessions."""

from collections.abc import Mapping
from datetime import datetime, timedelta
from uuid import UUID

from operator_retained_fixture import retained_id
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.requests.context import GoalSnapshot, HelpSnapshot, RequestContext
from studymate.domain.study_context import (
    CanonicalSubjectRef,
    GoalContent,
    HelpRevision,
    HelpSubject,
    HelpSubjects,
    StudyGoal,
)
from studymate.infrastructure.persistence.block_models import RelationshipRecord
from studymate.infrastructure.persistence.conversation_models import ConversationRecord
from studymate.infrastructure.persistence.goal_models import (
    GoalRecord,
    GoalRevisionRecord,
)
from studymate.infrastructure.persistence.message_models import (
    MessageOperationRecord,
    MessageRecord,
)
from studymate.infrastructure.requests.codec import encode_context
from studymate.infrastructure.requests.models import (
    ConnectionRequestRecord,
    RequestPreviewRecord,
    RequestRevisionRecord,
)


async def _retained_conversation(
    engine: AsyncEngine,
    namespace: str,
    targets: Mapping[str, str],
    at: datetime,
    count: int,
) -> dict[str, str]:
    sender, recipient = UUID(targets["hidden_id"]), UUID(targets["active_id"])
    low, high = sorted((sender, recipient))
    goal, preview, request, pair, conversation = (
        retained_id(namespace, label)
        for label in ("source-goal", "preview", "request", "pair", "conversation")
    )
    content = GoalContent(CanonicalSubjectRef(UUID(int=31)), topic="JOINs")
    context = RequestContext(
        sender,
        recipient,
        DiscoveryMode.FIND_HELP,
        sender_goal=GoalSnapshot(StudyGoal(goal, sender, 1, content, at, at), "SQL"),
        recipient_help=HelpSnapshot(
            HelpRevision(recipient, 1, HelpSubjects((HelpSubject(UUID(int=31)),)), at),
            ("SQL",),
        ),
    )
    async with async_sessionmaker(engine).begin() as session:
        session.add(
            GoalRecord(
                id=goal,
                account_id=sender,
                current_version=1,
                created_at=at,
                completed_at=None,
            )
        )
        await session.flush()
        session.add(
            GoalRevisionRecord(
                goal_id=goal,
                account_id=sender,
                version=1,
                subject_id=UUID(int=31),
                subject_label="SQL",
                topic="JOINs",
                topic_match_key="joins",
                context=None,
                shared_learning=False,
                saved_at=at,
                completed_at=None,
            )
        )
        session.add(RelationshipRecord(id=pair, low_id=low, high_id=high))
        await session.flush()
        session.add(
            RequestPreviewRecord(
                id=preview,
                sender_id=sender,
                recipient_id=recipient,
                mode="find_help",
                subject_id=UUID(int=31),
                created_at=at,
                source_json=encode_context(context),
                sender_goal_id=goal,
                sender_goal_version=1,
                recipient_goal_id=None,
                recipient_goal_version=None,
                sender_help_version=None,
                recipient_help_version=1,
            )
        )
        await session.flush()
        session.add(
            ConnectionRequestRecord(
                id=request,
                relationship_id=pair,
                low_id=low,
                high_id=high,
                sender_id=sender,
                recipient_id=recipient,
                preview_id=preview,
                request_text="Retained SQL practice request",
                note=None,
                sent_at=at,
                expires_at=at + timedelta(days=7),
                current_version=2,
                state="accepted",
                decision_sequence=1,
                request_id=None,
                action_id=None,
                trace_id=None,
                span_id=None,
            )
        )
        await session.flush()
        session.add(
            ConversationRecord(
                id=conversation,
                relationship_id=pair,
                low_id=low,
                high_id=high,
                request_id=request,
                accepted_request_version=2,
                request_state="accepted",
                next_message_sequence=count + 1,
            )
        )
        session.add_all(
            (
                RequestRevisionRecord(
                    request_id=request,
                    version=1,
                    state="pending",
                    changed_at=at,
                    decline_until=None,
                    conversation_id=None,
                ),
                RequestRevisionRecord(
                    request_id=request,
                    version=2,
                    state="accepted",
                    changed_at=at + timedelta(seconds=1),
                    decline_until=None,
                    conversation_id=conversation,
                ),
            )
        )
        await session.flush()
        for sequence in range(1, count + 1):
            author = sender if sequence % 2 else recipient
            operation, message, client = (
                retained_id(namespace, f"{kind}/{sequence}")
                for kind in ("operation", "message", "client-message")
            )
            session.add(
                MessageOperationRecord(
                    id=operation,
                    conversation_id=conversation,
                    low_id=low,
                    high_id=high,
                    author_id=author,
                    client_message_id=client,
                    state="confirmed",
                    message_id=message,
                    cancelled_at=None,
                )
            )
            await session.flush()
            session.add(
                MessageRecord(
                    id=message,
                    operation_id=operation,
                    conversation_id=conversation,
                    low_id=low,
                    high_id=high,
                    author_id=author,
                    client_message_id=client,
                    state="confirmed",
                    sequence=sequence,
                    text=f"Stored message {sequence}: <b>literal SQL</b>\nOriginal spacing",
                    sent_at=at + timedelta(seconds=sequence + 1),
                )
            )
    return {
        "conversation_id": str(conversation),
        "conversation_request_id": str(request),
        "conversation_relationship_id": str(pair),
        "conversation_low_id": str(low),
        "conversation_high_id": str(high),
    }


# These imports support only the controlled fixture seed/state boundary.
from hashlib import sha256
from io import BytesIO
from uuid import uuid4
from zoneinfo import ZoneInfo

from media_fixture import ControlledMedia
from operator_retained_fixture import SOURCE_TIME, seed_retained_targets
from PIL import Image
from sqlalchemy import func, select
from studymate.application.feedback.assessments import SaveFeedback, SaveFeedbackCommand
from studymate.application.feedback.outcomes import (
    SaveStudyOutcome,
    StudyOutcomeCommand,
)
from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import SessionCredential
from studymate.domain.feedback.assessments import (
    FeedbackContent,
    FeedbackDescriptor,
    StudyAgain,
)
from studymate.domain.feedback.outcomes import StudyAnswer
from studymate.domain.media import MediaObjectKind, MediaObjectRef
from studymate.infrastructure.feedback.models import (
    PeerFeedbackRecord,
    PeerFeedbackRevisionRecord,
    StudyOutcomeRevisionRecord,
    StudyPromptReceiptRecord,
)
from studymate.infrastructure.feedback.transactions import (
    FeedbackRecorders,
    SqlFeedbackUnitOfWork,
)
from studymate.infrastructure.persistence.identity_models import SessionRecord
from studymate.infrastructure.persistence.onboarding_models import (
    ProfileActivationRecord,
    VisibilityRevisionRecord,
)
from studymate.infrastructure.persistence.photo_attempt_models import PhotoAttemptRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import (
    record_peer_feedback,
    record_study_outcome,
    record_study_prompt,
)
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher

STUDY_NAMESPACES = frozenset(
    f"study/{case}/{project}"
    for case in ("offered", "eligible", "private", "current")
    for project in ("chromium-mobile", "webkit-mobile", "chromium-desktop")
)


def _display() -> bytes:
    with Image.new("RGB", (64, 64), (180, 180, 180)) as image:
        output = BytesIO()
        image.save(output, format="JPEG")
        return output.getvalue()


async def seed_study(
    engine: AsyncEngine, storage: ControlledMedia, namespace: str
) -> dict[str, str]:
    if namespace not in STUDY_NAMESPACES:
        raise ValueError("Unsupported controlled study namespace")
    targets = await seed_retained_targets(engine, namespace)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        now = await session.scalar(select(func.clock_timestamp()))
    if not isinstance(now, datetime):
        raise TypeError("Study fixture requires actual database clock")
    case = namespace.split("/")[1]
    at = (
        (now - timedelta(minutes=2)).replace(second=0, microsecond=0)
        if case == "eligible"
        else SOURCE_TIME + timedelta(days=3, minutes=1)
    )
    count = 1 if case == "private" else 2
    source = await _retained_conversation(engine, namespace, targets, at, count)
    viewer, peer = UUID(targets["hidden_id"]), UUID(targets["active_id"])
    viewer_token, peer_token = (
        SessionCredential(uuid4().hex + uuid4().hex[:11]) for _ in range(2)
    )
    hasher = Sha256SessionHasher()
    display = _display()
    async with sessions.begin() as session:
        # Historical pair acceptance precedes the actual retained hide revision.
        initial = await session.get(VisibilityRevisionRecord, (viewer, 1))
        activation = await session.get(ProfileActivationRecord, viewer)
        if initial is None or activation is None:
            raise RuntimeError("Controlled study activation missing")
        initial.hidden_at = None
        initial.changed_at = initial.completed_at
        session.add(
            VisibilityRevisionRecord(
                account_id=viewer,
                version=2,
                completed_at=initial.completed_at,
                hidden_at=at + timedelta(minutes=1),
                changed_at=at + timedelta(minutes=1),
            )
        )
        await session.flush()
        activation.visibility_version = 2
        for label, owner, credential in (
            ("hidden", viewer, viewer_token),
            ("active", peer, peer_token),
        ):
            session.add(
                SessionRecord(
                    id=retained_id(namespace, label + "/live-session"),
                    account_id=owner,
                    secret_digest=await hasher.digest(credential),
                    issued_at=now - timedelta(minutes=1),
                    expires_at=now + timedelta(hours=1),
                )
            )
            attempt = await session.get(
                PhotoAttemptRecord, retained_id(namespace, label + "/attempt")
            )
            if attempt is None:
                raise RuntimeError("Controlled photo attempt missing")
            attempt.display_width = 64
            attempt.display_height = 64
            attempt.display_size = len(display)
            attempt.display_digest = sha256(display).digest()
            await storage.retain(
                MediaObjectRef(
                    retained_id(namespace, label + "/upload"),
                    MediaObjectKind.DISPLAY,
                    attempt.id,
                ),
                display,
                "image/jpeg",
            )
    if case == "current":
        work = SqlFeedbackUnitOfWork(
            sessions,
            FeedbackRecorders(
                record_study_outcome, record_peer_feedback, record_study_prompt
            ),
        )
        fingerprint = HmacIntentFingerprinter(bytes.fromhex("03" * 32))
        conversation_id = UUID(source["conversation_id"])
        await SaveStudyOutcome(work, hasher, fingerprint)(
            StudyOutcomeCommand(
                viewer_token,
                conversation_id,
                StudyAnswer.YES,
                0,
                IntentKey(str(retained_id(namespace, "initial-outcome"))),
            )
        )
        await SaveFeedback(work, hasher, fingerprint)(
            SaveFeedbackCommand(
                viewer_token,
                conversation_id,
                FeedbackContent(
                    StudyAgain.YES,
                    (FeedbackDescriptor.SUPPORTIVE,),
                    "We practised SQL together.",
                ),
                0,
                IntentKey(str(retained_id(namespace, "initial-feedback"))),
            )
        )
    local = at.astimezone(ZoneInfo("Asia/Kuala_Lumpur"))
    browser = (local + timedelta(days=1)).replace(
        hour=12, minute=0, second=0, microsecond=0
    )
    return {
        **source,
        "viewer_id": str(viewer),
        "viewer_session": viewer_token.value,
        "peer_id": str(peer),
        "peer_session": peer_token.value,
        "browser_time": browser.isoformat(),
        "message_count": str(count),
    }


async def study_state(
    engine: AsyncEngine, conversation_id: UUID, actor_id: UUID
) -> dict[str, int]:
    async with async_sessionmaker(engine)() as session:
        outcomes = await session.scalar(
            select(func.count())
            .select_from(StudyOutcomeRevisionRecord)
            .where(
                StudyOutcomeRevisionRecord.actor_id == actor_id,
                StudyOutcomeRevisionRecord.conversation_id == conversation_id,
            )
        )
        revisions = await session.scalar(
            select(func.count())
            .select_from(PeerFeedbackRevisionRecord)
            .where(PeerFeedbackRevisionRecord.reviewer_id == actor_id)
        )
        current = await session.scalar(
            select(func.count())
            .select_from(PeerFeedbackRecord)
            .where(PeerFeedbackRecord.reviewer_id == actor_id)
        )
        prompts = await session.scalar(
            select(func.count())
            .select_from(StudyPromptReceiptRecord)
            .where(
                StudyPromptReceiptRecord.actor_id == actor_id,
                StudyPromptReceiptRecord.conversation_id == conversation_id,
            )
        )
        events = await session.scalar(
            select(func.count())
            .select_from(ProductEventRecord)
            .where(
                ProductEventRecord.account_id == actor_id,
                ProductEventRecord.kind.in_(
                    ("study.reported", "feedback.saved", "study.prompt_offered")
                ),
            )
        )
    if (
        not isinstance(outcomes, int)
        or not isinstance(revisions, int)
        or not isinstance(current, int)
        or not isinstance(prompts, int)
        or not isinstance(events, int)
    ):
        raise TypeError("Controlled study counts unavailable")
    return {
        "outcome_versions": outcomes,
        "feedback_versions": revisions,
        "feedback_current": current,
        "prompt_receipts": prompts,
        "canonical_events": events,
    }
