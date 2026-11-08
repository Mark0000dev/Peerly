from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Boolean, Integer, Nullable, Select, and_, cast, func, literal, or_, select
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement

from studymate.application.discovery.cursors import DiscoveryCursor, DiscoveryView
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.discovery_context import DiscoveryContext
from studymate.domain.discovery_order import MAX_FRESHNESS_BUCKET
from studymate.infrastructure.persistence.block_models import (
    BlockRecord,
    BlockRevisionRecord,
    RelationshipRecord,
)
from studymate.infrastructure.persistence.conversation_models import ConversationRecord
from studymate.infrastructure.persistence.discovery_freshness_models import DiscoveryExposureRecord
from studymate.infrastructure.persistence.discovery_pass_models import (
    DiscoveryContextRecord,
    PrivatePassRecord,
    PrivatePassRevisionRecord,
)
from studymate.infrastructure.persistence.goal_models import GoalRecord, GoalRevisionRecord
from studymate.infrastructure.persistence.help_models import HelpRecord, HelpSelectionRecord
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
)
from studymate.infrastructure.persistence.media_models import PhotoRecord, PhotoRevisionRecord
from studymate.infrastructure.persistence.onboarding_models import (
    ProfileActivationRecord,
    VisibilityRevisionRecord,
)
from studymate.infrastructure.persistence.profile_models import ProfileRecord, ProfileRevisionRecord
from studymate.infrastructure.persistence.registration_models import RegistrationReceiptRecord
from studymate.infrastructure.requests.models import ConnectionRequestRecord, RequestRevisionRecord

type CandidateSelect = Select[
    InstitutionalBindingRecord,
    ProfileRevisionRecord,
    PhotoRevisionRecord,
    GoalRecord | None,
    GoalRevisionRecord | None,
    VisibilityRevisionRecord,
    DiscoveryExposureRecord,
    bool,
    int,
    int | None,
]


def _relevance(context: DiscoveryContext) -> tuple[ColumnElement[bool], ColumnElement[bool]]:
    if context.mode == DiscoveryMode.OFFER_HELP:
        help_for_goal = (
            select(HelpSelectionRecord.account_id)
            .where(
                HelpSelectionRecord.account_id == context.account_id,
                HelpSelectionRecord.version == context.help_version,
                HelpSelectionRecord.subject_id == GoalRevisionRecord.subject_id,
            )
            .correlate(GoalRevisionRecord)
        )
        topic: ColumnElement[bool] = help_for_goal.where(
            HelpSelectionRecord.topic_match_key.is_not(None),
            HelpSelectionRecord.topic_match_key == GoalRevisionRecord.topic_match_key,
        ).exists()
        return help_for_goal.exists(), topic
    own = aliased(GoalRevisionRecord)
    source = select(own.subject_id).where(
        own.account_id == context.account_id,
        own.goal_id == context.goal_id,
        own.version == context.goal_version,
    )
    subject = source.scalar_subquery()
    key = source.with_only_columns(own.topic_match_key).scalar_subquery()
    if context.mode == DiscoveryMode.STUDY_TOGETHER:
        relevant = and_(
            GoalRevisionRecord.subject_id == subject, GoalRevisionRecord.shared_learning.is_(True)
        )
        topic = cast(func.coalesce(GoalRevisionRecord.topic_match_key == key, False), Boolean)
        return relevant, topic
    helper = (
        select(HelpSelectionRecord.account_id)
        .join(
            HelpRecord,
            (HelpRecord.account_id == HelpSelectionRecord.account_id)
            & (HelpRecord.current_version == HelpSelectionRecord.version),
        )
        .where(
            HelpSelectionRecord.account_id == AccountRecord.id,
            HelpSelectionRecord.subject_id == subject,
        )
        .correlate(AccountRecord)
    )
    return helper.exists(), helper.where(
        HelpSelectionRecord.topic_match_key.is_not(None), HelpSelectionRecord.topic_match_key == key
    ).exists()


def _pair(context: DiscoveryContext) -> ColumnElement[bool]:
    return or_(
        and_(
            RelationshipRecord.low_id == context.account_id,
            RelationshipRecord.high_id == AccountRecord.id,
        ),
        and_(
            RelationshipRecord.high_id == context.account_id,
            RelationshipRecord.low_id == AccountRecord.id,
        ),
    )


def _blocked(context: DiscoveryContext) -> ColumnElement[bool]:
    return (
        select(RelationshipRecord.id)
        .join(BlockRecord, BlockRecord.relationship_id == RelationshipRecord.id)
        .join(
            BlockRevisionRecord,
            (BlockRevisionRecord.relationship_id == BlockRecord.relationship_id)
            & (BlockRevisionRecord.blocker_id == BlockRecord.blocker_id)
            & (BlockRevisionRecord.version == BlockRecord.current_version),
        )
        .where(_pair(context), BlockRevisionRecord.blocked.is_(True))
        .correlate(AccountRecord)
        .exists()
    )


def _connected(context: DiscoveryContext) -> ColumnElement[bool]:
    return (
        select(RelationshipRecord.id)
        .join(ConversationRecord, ConversationRecord.relationship_id == RelationshipRecord.id)
        .where(_pair(context))
        .correlate(AccountRecord)
        .exists()
    )


def _pending(context: DiscoveryContext, at: datetime) -> ColumnElement[bool]:
    return (
        select(RelationshipRecord.id)
        .join(
            ConnectionRequestRecord,
            ConnectionRequestRecord.relationship_id == RelationshipRecord.id,
        )
        .join(
            RequestRevisionRecord,
            (RequestRevisionRecord.request_id == ConnectionRequestRecord.id)
            & (RequestRevisionRecord.version == ConnectionRequestRecord.current_version),
        )
        .where(
            _pair(context),
            ConnectionRequestRecord.expires_at > at,
            or_(
                ConnectionRequestRecord.state == "pending",
                and_(
                    ConnectionRequestRecord.state == "pending_decline",
                    RequestRevisionRecord.decline_until > at,
                ),
            ),
        )
        .correlate(AccountRecord)
        .exists()
    )


def _passed(context: DiscoveryContext) -> ColumnElement[bool]:
    return (
        select(PrivatePassRecord.id)
        .join(DiscoveryContextRecord, DiscoveryContextRecord.id == PrivatePassRecord.context_id)
        .join(
            PrivatePassRevisionRecord,
            (PrivatePassRevisionRecord.pass_id == PrivatePassRecord.id)
            & (PrivatePassRevisionRecord.version == PrivatePassRecord.current_version),
        )
        .where(
            DiscoveryContextRecord.account_id == context.account_id,
            DiscoveryContextRecord.mode == context.mode.value,
            DiscoveryContextRecord.goal_id == context.goal_id,
            DiscoveryContextRecord.goal_version == context.goal_version,
            DiscoveryContextRecord.help_version == context.help_version,
            PrivatePassRecord.target_id == AccountRecord.id,
            PrivatePassRevisionRecord.passed.is_(True),
        )
        .correlate(AccountRecord)
        .exists()
    )


@dataclass(frozen=True, slots=True)
class DiscoveryQuery:
    context: DiscoveryContext
    view: DiscoveryView
    as_of: datetime
    now: datetime
    cursor: DiscoveryCursor | None = None

    def statement(self, limit: int, *, include_decisions: bool = True) -> CandidateSelect:
        relevant, topic = _relevance(self.context)
        candidate_help = aliased(HelpRecord)
        freshness = cast(
            func.greatest(
                0,
                func.least(
                    MAX_FRESHNESS_BUCKET,
                    func.floor(
                        func.extract(
                            "epoch", literal(self.as_of) - DiscoveryExposureRecord.last_activity_at
                        )
                        / 86400
                    ),
                ),
            ),
            Integer,
        )
        statement = (
            select(
                InstitutionalBindingRecord,
                ProfileRevisionRecord,
                PhotoRevisionRecord,
                Nullable(GoalRecord),
                Nullable(GoalRevisionRecord),
                VisibilityRevisionRecord,
                DiscoveryExposureRecord,
                topic,
                freshness,
                Nullable(candidate_help.current_version),
            )
            .select_from(AccountRecord)
            .join(
                InstitutionalBindingRecord,
                InstitutionalBindingRecord.account_id == AccountRecord.id,
            )
            .join(ProfileRecord, ProfileRecord.account_id == AccountRecord.id)
            .join(
                ProfileRevisionRecord,
                (ProfileRevisionRecord.account_id == AccountRecord.id)
                & (ProfileRevisionRecord.version == ProfileRecord.current_version),
            )
            .join(PhotoRecord, PhotoRecord.account_id == AccountRecord.id)
            .join(
                PhotoRevisionRecord,
                (PhotoRevisionRecord.account_id == AccountRecord.id)
                & (PhotoRevisionRecord.version == PhotoRecord.current_version),
            )
            .join(ProfileActivationRecord, ProfileActivationRecord.account_id == AccountRecord.id)
            .join(
                RegistrationReceiptRecord,
                RegistrationReceiptRecord.id == ProfileActivationRecord.registration_id,
            )
            .join(
                VisibilityRevisionRecord,
                (VisibilityRevisionRecord.account_id == AccountRecord.id)
                & (VisibilityRevisionRecord.version == ProfileActivationRecord.visibility_version),
            )
            .join(DiscoveryExposureRecord, DiscoveryExposureRecord.account_id == AccountRecord.id)
            .outerjoin(
                GoalRecord,
                (GoalRecord.account_id == AccountRecord.id) & GoalRecord.completed_at.is_(None),
            )
            .outerjoin(
                GoalRevisionRecord,
                (GoalRevisionRecord.goal_id == GoalRecord.id)
                & (GoalRevisionRecord.version == GoalRecord.current_version),
            )
            .outerjoin(candidate_help, candidate_help.account_id == AccountRecord.id)
            .where(
                AccountRecord.id != self.context.account_id,
                AccountRecord.banned_at.is_(None),
                AccountRecord.deleted_at.is_(None),
                InstitutionalBindingRecord.revoked_at.is_(None),
                ProfileRevisionRecord.display_name.is_not(None),
                VisibilityRevisionRecord.hidden_at.is_(None),
                DiscoveryExposureRecord.paused_at.is_(None),
                func.extract("epoch", literal(self.now) - DiscoveryExposureRecord.last_activity_at)
                < DiscoveryExposureRecord.inactivity_seconds,
                relevant,
                ~_blocked(self.context),
                ~_connected(self.context),
            )
        )
        if include_decisions:
            passed = _passed(self.context)
            statement = statement.where(
                passed if self.view == DiscoveryView.PASSED else ~passed,
                ~_pending(self.context, self.now),
            )
            if self.cursor is not None:
                position = self.cursor.position
                statement = statement.where(
                    or_(
                        topic < literal(position.same_topic),
                        and_(topic == position.same_topic, freshness > position.freshness),
                        and_(
                            topic == position.same_topic,
                            freshness == position.freshness,
                            AccountRecord.id > position.person_id,
                        ),
                    )
                )
        return statement.order_by(topic.desc(), freshness, AccountRecord.id).limit(limit)
