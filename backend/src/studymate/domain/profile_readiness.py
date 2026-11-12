"""Server-derived prerequisites, independent of future pair/resource permissions."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from studymate.domain.membership import IdentityCapabilities, Membership, identity_capabilities
from studymate.domain.profiles import OnboardingTask, ProfileBasics
from studymate.domain.study_context import HelpSubjects, StudyGoal
from studymate.domain.time import require_aware


class RestoreRequirement(StrEnum):
    PHOTO = "photo"
    PHOTO_REVIEW = "photo_review"
    STUDY_CONTEXT = "study_context"


class OnboardingRequirement(StrEnum):
    DISPLAY_NAME = "display_name"
    PHOTO = "photo"
    STUDY_GOAL = "study_goal"
    HELP_SUBJECTS = "help_subjects"


@dataclass(frozen=True, slots=True)
class StudentProfileState:
    """Owned read projection; processing/lifecycle facts are never client writes."""

    account_id: UUID
    basics: ProfileBasics
    photo_ready: bool
    task: OnboardingTask
    goal: StudyGoal | None
    help_subjects: HelpSubjects
    completed_at: datetime | None = None
    hidden_at: datetime | None = None
    photo_replacement_required: bool = False

    def __post_init__(self) -> None:
        if self.goal is not None and self.goal.account_id != self.account_id:
            raise ValueError("Profile study context owner mismatch")
        if self.completed_at is not None:
            require_aware(self.completed_at)
            if self.basics.display_name is None:
                raise ValueError("Completed profile requires its saved display name")
        if self.hidden_at is not None:
            require_aware(self.hidden_at)

    @property
    def has_study_context(self) -> bool:
        return (self.goal is not None and self.goal.active) or bool(self.help_subjects.values)

    @property
    def exposure_requirements(self) -> tuple[RestoreRequirement, ...]:
        missing: list[RestoreRequirement] = []
        if not self.photo_ready:
            missing.append(RestoreRequirement.PHOTO)
        if self.photo_replacement_required:
            missing.append(RestoreRequirement.PHOTO_REVIEW)
        if not self.has_study_context:
            missing.append(RestoreRequirement.STUDY_CONTEXT)
        return tuple(missing)

    @property
    def initial_requirements(self) -> tuple[OnboardingRequirement, ...]:
        missing: list[OnboardingRequirement] = []
        if self.basics.display_name is None:
            missing.append(OnboardingRequirement.DISPLAY_NAME)
        if not self.photo_ready:
            missing.append(OnboardingRequirement.PHOTO)
        if self.task == OnboardingTask.FIND_HELP and (self.goal is None or not self.goal.active):
            missing.append(OnboardingRequirement.STUDY_GOAL)
        if self.task == OnboardingTask.OFFER_HELP and not self.help_subjects.values:
            missing.append(OnboardingRequirement.HELP_SUBJECTS)
        return tuple(missing)


@dataclass(frozen=True, slots=True)
class ProfileCapabilities:
    identity: IdentityCapabilities
    can_manage_profile: bool
    can_complete_setup: bool
    can_complete_registration: bool
    can_discover: bool
    can_make_new_contacts: bool
    can_access_existing_chats: bool
    setup_requirements: tuple[OnboardingRequirement, ...]
    can_hide_profile: bool
    can_restore_profile: bool
    restore_requirements: tuple[RestoreRequirement, ...]


def profile_capabilities(
    *,
    membership: Membership | None,
    banned: bool,
    deleted: bool,
    registered: bool,
    profile: StudentProfileState,
) -> ProfileCapabilities:
    activated = registered and profile.completed_at is not None
    identity = identity_capabilities(
        membership=membership, banned=banned or deleted, activation_complete=activated
    )
    initial = profile.initial_requirements
    discover = (
        identity.can_use_student_features
        and profile.hidden_at is None
        and profile.photo_ready
        and not profile.photo_replacement_required
        and profile.has_study_context
    )
    restore = profile.exposure_requirements if profile.hidden_at is not None else ()
    return ProfileCapabilities(
        identity=identity,
        can_manage_profile=identity.can_begin_onboarding,
        can_complete_setup=identity.can_begin_onboarding and not activated and not initial,
        can_complete_registration=identity.can_begin_onboarding and not registered and not initial,
        can_discover=discover,
        can_make_new_contacts=discover,
        can_access_existing_chats=identity.can_use_student_features,
        setup_requirements=() if activated else initial,
        can_hide_profile=identity.can_use_student_features and profile.hidden_at is None,
        can_restore_profile=identity.can_use_student_features
        and profile.hidden_at is not None
        and not restore,
        restore_requirements=tuple(restore),
    )
