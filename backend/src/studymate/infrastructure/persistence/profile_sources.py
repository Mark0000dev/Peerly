"""Bounded current source projections, never an authorization grant or disclosure."""

from datetime import timedelta
from uuid import UUID

from sqlalchemy import Nullable, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.application.discovery.profiles import DiscoveryProfileSource
from studymate.application.profiles.help_subjects import SavedHelpSubjects
from studymate.application.profiles.onboarding import ProfileSetupSnapshot
from studymate.domain.discovery_freshness import DiscoveryExposure
from studymate.domain.identity import StudentEmail
from studymate.domain.media import PhotoRevision
from studymate.domain.membership import Membership
from studymate.domain.onboarding import ProfileLifecycle
from studymate.domain.profiles import (
    DisplayName,
    LanguageCode,
    OnboardingTask,
    ProfileBasics,
    ProfileRevision,
)
from studymate.domain.study_context import HelpRevision, HelpSubject, HelpSubjects
from studymate.infrastructure.operator.photo_review_condition import read_photo_replacement_accounts
from studymate.infrastructure.persistence.block_models import (
    BlockRecord,
    BlockRevisionRecord,
    RelationshipRecord,
)
from studymate.infrastructure.persistence.discovery_exposure import read_freshness_policy
from studymate.infrastructure.persistence.discovery_freshness_models import DiscoveryExposureRecord
from studymate.infrastructure.persistence.goal_models import GoalRecord, GoalRevisionRecord
from studymate.infrastructure.persistence.goals import goal_value
from studymate.infrastructure.persistence.help_models import (
    HelpRecord,
    HelpRevisionRecord,
    HelpSelectionRecord,
)
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
)
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.media_models import PhotoRecord, PhotoRevisionRecord
from studymate.infrastructure.persistence.onboarding_models import (
    ProfileActivationRecord,
    VisibilityRevisionRecord,
)
from studymate.infrastructure.persistence.profile_models import (
    ProfileLanguageRecord,
    ProfileRecord,
    ProfileRevisionRecord,
)
from studymate.infrastructure.persistence.registration_models import RegistrationReceiptRecord

MAX_PROFILE_SOURCE_BATCH = 22


def _bounded(account_ids: tuple[UUID, ...]) -> tuple[UUID, ...]:
    if len(account_ids) > MAX_PROFILE_SOURCE_BATCH:
        raise ValueError("Profile source batch exceeds its bounded query scope")
    return tuple(dict.fromkeys(account_ids))


async def read_profile_languages(
    session: AsyncSession, profiles: tuple[ProfileRevisionRecord, ...]
) -> dict[UUID, tuple[LanguageCode, ...]]:
    rows = await session.scalars(
        select(ProfileLanguageRecord)
        .where(
            tuple_(ProfileLanguageRecord.account_id, ProfileLanguageRecord.version).in_(
                tuple((record.account_id, record.version) for record in profiles)
            )
        )
        .order_by(ProfileLanguageRecord.account_id, ProfileLanguageRecord.slot)
    )
    grouped: dict[UUID, list[LanguageCode]] = {}
    for record in rows:
        grouped.setdefault(record.account_id, []).append(LanguageCode(record.code))
    return {key: tuple(values) for key, values in grouped.items()}


async def read_help_versions(
    session: AsyncSession, versions: tuple[tuple[UUID, int], ...]
) -> dict[UUID, SavedHelpSubjects]:
    rows = await session.execute(
        select(HelpRevisionRecord, Nullable(HelpSelectionRecord))
        .outerjoin(
            HelpSelectionRecord,
            (HelpSelectionRecord.account_id == HelpRevisionRecord.account_id)
            & (HelpSelectionRecord.version == HelpRevisionRecord.version),
        )
        .where(tuple_(HelpRevisionRecord.account_id, HelpRevisionRecord.version).in_(versions))
        .order_by(HelpRevisionRecord.account_id, HelpSelectionRecord.slot)
    )
    revisions: dict[UUID, HelpRevisionRecord] = {}
    selections: dict[UUID, list[HelpSelectionRecord]] = {}
    for revision, item in rows:
        revisions[revision.account_id] = revision
        if item is not None:
            selections.setdefault(revision.account_id, []).append(item)
    return {
        account_id: SavedHelpSubjects(
            HelpRevision(
                account_id,
                revision.version,
                HelpSubjects(
                    tuple(
                        HelpSubject(item.subject_id, item.topic_note)
                        for item in selections.get(account_id, ())
                    )
                ),
                revision.saved_at,
            ),
            tuple(item.subject_label for item in selections.get(account_id, ())),
        )
        for account_id, revision in revisions.items()
    }


async def read_profile_sources(
    session: AsyncSession, account_ids: tuple[UUID, ...]
) -> dict[UUID, DiscoveryProfileSource]:
    ids = _bounded(account_ids)
    if not ids:
        return {}
    photo_replacements = await read_photo_replacement_accounts(session, ids)
    rows = (
        await session.execute(
            select(
                AccountRecord,
                Nullable(InstitutionalBindingRecord),
                Nullable(ProfileRevisionRecord),
                Nullable(PhotoRevisionRecord),
                Nullable(GoalRecord),
                Nullable(GoalRevisionRecord),
                Nullable(VisibilityRevisionRecord),
                Nullable(DiscoveryExposureRecord),
                Nullable(RegistrationReceiptRecord),
                Nullable(HelpRecord.current_version),
            )
            .select_from(AccountRecord)
            .outerjoin(
                InstitutionalBindingRecord,
                InstitutionalBindingRecord.account_id == AccountRecord.id,
            )
            .outerjoin(ProfileRecord, ProfileRecord.account_id == AccountRecord.id)
            .outerjoin(
                ProfileRevisionRecord,
                (ProfileRevisionRecord.account_id == AccountRecord.id)
                & (ProfileRevisionRecord.version == ProfileRecord.current_version),
            )
            .outerjoin(PhotoRecord, PhotoRecord.account_id == AccountRecord.id)
            .outerjoin(
                PhotoRevisionRecord,
                (PhotoRevisionRecord.account_id == AccountRecord.id)
                & (PhotoRevisionRecord.version == PhotoRecord.current_version),
            )
            .outerjoin(
                GoalRecord,
                (GoalRecord.account_id == AccountRecord.id) & GoalRecord.completed_at.is_(None),
            )
            .outerjoin(
                GoalRevisionRecord,
                (GoalRevisionRecord.goal_id == GoalRecord.id)
                & (GoalRevisionRecord.version == GoalRecord.current_version),
            )
            .outerjoin(
                ProfileActivationRecord, ProfileActivationRecord.account_id == AccountRecord.id
            )
            .outerjoin(
                VisibilityRevisionRecord,
                (VisibilityRevisionRecord.account_id == AccountRecord.id)
                & (VisibilityRevisionRecord.version == ProfileActivationRecord.visibility_version),
            )
            .outerjoin(
                DiscoveryExposureRecord, DiscoveryExposureRecord.account_id == AccountRecord.id
            )
            .outerjoin(
                RegistrationReceiptRecord, RegistrationReceiptRecord.account_id == AccountRecord.id
            )
            .outerjoin(HelpRecord, HelpRecord.account_id == AccountRecord.id)
            .where(AccountRecord.id.in_(ids))
        )
    ).all()
    languages = await read_profile_languages(
        session, tuple(row[2] for row in rows if row[2] is not None)
    )
    helpers = await read_help_versions(
        session, tuple((row[0].id, row[9]) for row in rows if row[9] is not None)
    )
    policy = await read_freshness_policy(session, await SqlIdentityTransaction(session).now())
    result: dict[UUID, DiscoveryProfileSource] = {}
    for (
        account,
        binding,
        profile,
        photo,
        goal,
        goal_revision,
        lifecycle,
        exposure,
        registration,
        _help_version,
    ) in rows:
        account_id = account.id
        setup = ProfileSetupSnapshot(
            account_id,
            ProfileRevision(
                account_id,
                profile.version,
                ProfileBasics(
                    DisplayName(profile.display_name) if profile.display_name is not None else None,
                    profile.about,
                    profile.programme,
                    profile.year_label,
                    languages.get(account_id, ()),
                ),
                OnboardingTask(profile.task),
                profile.saved_at,
            )
            if profile is not None
            else None,
            PhotoRevision(account_id, photo.version, photo.upload_id, photo.saved_at)
            if photo is not None
            else None,
            goal_value(goal, goal_revision)
            if goal is not None and goal_revision is not None
            else None,
            helpers.get(account_id),
            ProfileLifecycle(
                account_id,
                lifecycle.completed_at,
                lifecycle.version,
                lifecycle.hidden_at,
                lifecycle.changed_at,
            )
            if lifecycle is not None
            else None,
            DiscoveryExposure(
                account_id,
                exposure.last_activity_at,
                exposure.confirmed_at,
                exposure.paused_at,
                timedelta(seconds=exposure.inactivity_seconds),
            )
            if exposure is not None
            else None,
            policy,
            account_id in photo_replacements,
        )
        result[account_id] = DiscoveryProfileSource(
            setup,
            Membership(StudentEmail(binding.email), binding.verified_at, binding.revoked_at)
            if binding is not None
            else None,
            registration is not None,
            account.banned_at is not None,
            account.deleted_at is not None,
        )
    return result


async def read_blocked_peers(
    session: AsyncSession, actor_id: UUID, peer_ids: tuple[UUID, ...]
) -> frozenset[UUID]:
    ids = _bounded(peer_ids)
    if not ids:
        return frozenset()
    rows = await session.execute(
        select(RelationshipRecord.low_id, RelationshipRecord.high_id)
        .join(BlockRecord, BlockRecord.relationship_id == RelationshipRecord.id)
        .join(
            BlockRevisionRecord,
            (BlockRevisionRecord.relationship_id == BlockRecord.relationship_id)
            & (BlockRevisionRecord.blocker_id == BlockRecord.blocker_id)
            & (BlockRevisionRecord.version == BlockRecord.current_version),
        )
        .where(
            BlockRevisionRecord.blocked.is_(True),
            or_(
                (RelationshipRecord.low_id == actor_id) & RelationshipRecord.high_id.in_(ids),
                (RelationshipRecord.high_id == actor_id) & RelationshipRecord.low_id.in_(ids),
            ),
        )
    )
    return frozenset(high if low == actor_id else low for low, high in rows)
