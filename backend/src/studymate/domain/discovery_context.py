"""Private discovery decisions bind to real saved declarations, never a UI role."""

from dataclasses import dataclass
from uuid import UUID

from studymate.domain.discovery import DiscoveryMode
from studymate.domain.study_context import HelpRevision, StudyGoal


@dataclass(frozen=True, slots=True)
class DiscoveryScope:
    mode: DiscoveryMode
    goal_id: UUID | None
    goal_version: int | None
    help_version: int | None

    def __post_init__(self) -> None:
        if self.mode == DiscoveryMode.OFFER_HELP:
            if self.goal_id is not None or self.goal_version is not None:
                raise ValueError("Offer-help context uses the saved help declaration")
            version = self.help_version
        else:
            if self.goal_id is None or self.help_version is not None:
                raise ValueError("Learning context uses the saved active goal")
            version = self.goal_version
        if version is None or isinstance(version, bool) or version < 1:
            raise ValueError("Discovery context needs a positive saved revision")

    def bind(self, account_id: UUID) -> "DiscoveryContext":
        return DiscoveryContext(
            account_id, self.mode, self.goal_id, self.goal_version, self.help_version
        )


@dataclass(frozen=True, slots=True)
class DiscoveryContext:
    account_id: UUID
    mode: DiscoveryMode
    goal_id: UUID | None
    goal_version: int | None
    help_version: int | None

    def __post_init__(self) -> None:
        DiscoveryScope(self.mode, self.goal_id, self.goal_version, self.help_version)

    @property
    def scope(self) -> DiscoveryScope:
        return DiscoveryScope(self.mode, self.goal_id, self.goal_version, self.help_version)


def discovery_context(
    account_id: UUID,
    mode: DiscoveryMode,
    goal: StudyGoal | None,
    help_revision: HelpRevision | None,
) -> DiscoveryContext | None:
    """Return a usable matching context; eligibility is independently authorised."""
    if goal is not None and goal.account_id != account_id:
        raise ValueError("Discovery goal belongs to another account")
    if help_revision is not None and help_revision.account_id != account_id:
        raise ValueError("Discovery help declaration belongs to another account")
    if mode == DiscoveryMode.OFFER_HELP:
        if help_revision is None or not help_revision.subjects.values:
            return None
        return DiscoveryContext(account_id, mode, None, None, help_revision.version)
    if goal is None or not goal.active or goal.content.canonical_subject_id is None:
        return None
    if mode == DiscoveryMode.STUDY_TOGETHER and not goal.content.shared_learning:
        return None
    return DiscoveryContext(account_id, mode, goal.id, goal.version, None)
