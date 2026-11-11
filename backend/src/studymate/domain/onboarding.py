from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from studymate.domain.media import PhotoRevision
from studymate.domain.profile_readiness import StudentProfileState
from studymate.domain.profiles import ProfileRevision
from studymate.domain.registration import RegistrationReceipt
from studymate.domain.study_context import HelpRevision, HelpSubjects, StudyGoal
from studymate.domain.time import require_aware


@dataclass(frozen=True, slots=True)
class ProfileLifecycle:
    account_id: UUID
    completed_at: datetime
    visibility_version: int
    hidden_at: datetime | None
    changed_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.completed_at)
        require_aware(self.changed_at)
        if isinstance(self.visibility_version, bool) or self.visibility_version < 1:
            raise ValueError("Visibility revision must be positive")
        if self.changed_at < self.completed_at:
            raise ValueError("Visibility cannot precede initial completion")
        if self.hidden_at is not None:
            require_aware(self.hidden_at)
            if not self.completed_at <= self.hidden_at <= self.changed_at:
                raise ValueError("Hidden time must belong to the completed profile history")

    @property
    def hidden(self) -> bool:
        return self.hidden_at is not None

    def with_visibility(self, *, hidden: bool, at: datetime) -> "ProfileLifecycle":
        require_aware(at)
        if at < self.changed_at:
            raise ValueError("Visibility action cannot precede its current revision")
        if hidden == self.hidden:
            return self
        return replace(
            self,
            visibility_version=self.visibility_version + 1,
            hidden_at=at if hidden else None,
            changed_at=at,
        )


@dataclass(frozen=True, slots=True)
class OnboardingActivation:
    profile: ProfileRevision
    photo: PhotoRevision
    goal: StudyGoal | None
    help_revision: HelpRevision | None
    registration: RegistrationReceipt
    completed_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.completed_at)
        account_id = self.profile.account_id
        if (
            self.photo.account_id != account_id
            or self.registration.account_id != account_id
            or (self.goal is not None and self.goal.account_id != account_id)
            or (self.help_revision is not None and self.help_revision.account_id != account_id)
        ):
            raise ValueError("Activation sources must belong to one account")
        timestamps = (
            self.profile.saved_at,
            self.photo.saved_at,
            self.registration.registered_at,
            *((self.goal.updated_at,) if self.goal is not None else ()),
            *((self.help_revision.saved_at,) if self.help_revision is not None else ()),
        )
        if any(at > self.completed_at for at in timestamps):
            raise ValueError("Activation cannot precede its recorded sources")
        state = StudentProfileState(
            account_id,
            self.profile.basics,
            True,
            self.profile.task,
            self.goal,
            self.help_revision.subjects if self.help_revision is not None else HelpSubjects(),
        )
        if state.initial_requirements:
            raise ValueError(
                "Activation requires a complete named profile and chosen study context"
            )
