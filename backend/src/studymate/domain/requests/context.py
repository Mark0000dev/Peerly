from dataclasses import dataclass, field
from uuid import UUID

from studymate.domain.discovery import DiscoveryMode
from studymate.domain.study_context import HelpRevision, StudyGoal
from studymate.domain.text import plain_text

MAX_REQUEST_TEXT = 240


@dataclass(frozen=True, slots=True)
class GoalSnapshot:
    goal: StudyGoal = field(repr=False)
    subject_label: str = field(repr=False)

    def __post_init__(self) -> None:
        plain_text(self.subject_label, minimum=1, maximum=80)
        if not self.goal.active or self.goal.content.canonical_subject_id is None:
            raise ValueError("Request goal must be active and canonical")


@dataclass(frozen=True, slots=True)
class HelpSnapshot:
    revision: HelpRevision = field(repr=False)
    labels: tuple[str, ...] = field(repr=False)

    def __post_init__(self) -> None:
        if len(self.labels) != len(self.revision.subjects.values):
            raise ValueError("Help labels must match the retained declaration")
        for label in self.labels:
            plain_text(label, minimum=1, maximum=80)

    def supports(self, subject_id: UUID) -> bool:
        return any(value.subject_id == subject_id for value in self.revision.subjects.values)


@dataclass(frozen=True, slots=True)
class RequestContext:
    sender_id: UUID
    recipient_id: UUID
    mode: DiscoveryMode
    sender_goal: GoalSnapshot | None = field(default=None, repr=False)
    recipient_goal: GoalSnapshot | None = field(default=None, repr=False)
    sender_help: HelpSnapshot | None = field(default=None, repr=False)
    recipient_help: HelpSnapshot | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.sender_id == self.recipient_id:
            raise ValueError("Requests need distinct participants")
        for owner, goal, help_snapshot in (
            (self.sender_id, self.sender_goal, self.sender_help),
            (self.recipient_id, self.recipient_goal, self.recipient_help),
        ):
            if goal is not None and goal.goal.account_id != owner:
                raise ValueError("Goal snapshot belongs to another account")
            if help_snapshot is not None and help_snapshot.revision.account_id != owner:
                raise ValueError("Help snapshot belongs to another account")
        self._validate_mode()

    def _validate_mode(self) -> None:
        first, second = self.sender_goal, self.recipient_goal
        if self.mode == DiscoveryMode.FIND_HELP:
            if (
                first is None
                or self.recipient_help is None
                or second is not None
                or self.sender_help is not None
            ):
                raise ValueError("Find-help snapshot needs sender goal and recipient help only")
            if not self.recipient_help.supports(self.subject_id):
                raise ValueError("Recipient has not declared help for this subject")
        elif self.mode == DiscoveryMode.OFFER_HELP:
            if (
                second is None
                or self.sender_help is None
                or first is not None
                or self.recipient_help is not None
            ):
                raise ValueError("Offer snapshot needs recipient goal and sender help only")
            if not self.sender_help.supports(self.subject_id):
                raise ValueError("Sender has not declared help for this subject")
        elif (
            first is None
            or second is None
            or self.sender_help is not None
            or self.recipient_help is not None
            or not first.goal.content.shared_learning
            or not second.goal.content.shared_learning
            or first.goal.content.canonical_subject_id != second.goal.content.canonical_subject_id
        ):
            raise ValueError("Study snapshot needs both shared goals in the same subject")

    @property
    def subject_id(self) -> UUID:
        goal = self.recipient_goal if self.mode == DiscoveryMode.OFFER_HELP else self.sender_goal
        subject = goal.goal.content.canonical_subject_id if goal is not None else None
        if subject is None:
            raise ValueError("Request context lacks a canonical subject")
        return subject


@dataclass(frozen=True, slots=True)
class RequestText:
    text: str = field(repr=False)
    note: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        for value in (self.text, self.note):
            if value is not None:
                if len(value) > MAX_REQUEST_TEXT:
                    raise ValueError("Request text exceeds240 code points")
                plain_text(value, minimum=1, maximum=MAX_REQUEST_TEXT, multiline=True)
