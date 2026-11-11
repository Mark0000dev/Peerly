"""Exact declared knowledge-area relevance; callers independently enforce access."""

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from studymate.domain.study_context import HelpSubject, HelpSubjects, StudyGoal


class DiscoveryMode(StrEnum):
    FIND_HELP = "find_help"
    OFFER_HELP = "offer_help"
    STUDY_TOGETHER = "study_together"


class RelevanceReason(StrEnum):
    CAN_HELP = "can_help"
    YOU_CAN_HELP = "you_can_help"
    SHARED_GOAL = "shared_goal"


@dataclass(frozen=True, slots=True)
class StudyDeclarations:
    account_id: UUID
    goal: StudyGoal | None = field(repr=False)
    help_subjects: HelpSubjects = field(repr=False)

    def __post_init__(self) -> None:
        if self.goal is not None and self.goal.account_id != self.account_id:
            raise ValueError("Discovery declarations must belong to their account")

    @property
    def active_goal(self) -> StudyGoal | None:
        return self.goal if self.goal is not None and self.goal.active else None

    def help_for(self, subject_id: UUID) -> HelpSubject | None:
        return next(
            (item for item in self.help_subjects.values if item.subject_id == subject_id), None
        )


@dataclass(frozen=True, slots=True)
class DiscoveryMatch:
    reason: RelevanceReason
    subject_id: UUID
    same_topic: bool
    reciprocal_subject_id: UUID | None


def topic_match_key(topic: str | None) -> str | None:
    """Literal Unicode/whitespace normalisation, never semantic topic inference."""
    return " ".join(topic.casefold().split()) if topic else None


def _same_topic(first: str | None, second: str | None) -> bool:
    key = topic_match_key(first)
    return bool(key and key == topic_match_key(second))


def _reciprocal_subject(viewer: StudyDeclarations, candidate: StudyDeclarations) -> UUID | None:
    goal = candidate.active_goal
    subject_id = goal.content.canonical_subject_id if goal is not None else None
    return (
        subject_id if subject_id is not None and viewer.help_for(subject_id) is not None else None
    )


def _find_help(viewer: StudyDeclarations, candidate: StudyDeclarations) -> DiscoveryMatch | None:
    goal = viewer.active_goal
    subject_id = goal.content.canonical_subject_id if goal is not None else None
    helper = candidate.help_for(subject_id) if subject_id is not None else None
    if goal is None or subject_id is None or helper is None:
        return None
    return DiscoveryMatch(
        RelevanceReason.CAN_HELP,
        subject_id,
        _same_topic(goal.content.topic, helper.topic_note),
        _reciprocal_subject(viewer, candidate),
    )


def _offer_help(viewer: StudyDeclarations, candidate: StudyDeclarations) -> DiscoveryMatch | None:
    forward = _find_help(candidate, viewer)
    if forward is None:
        return None
    return DiscoveryMatch(
        RelevanceReason.YOU_CAN_HELP,
        forward.subject_id,
        forward.same_topic,
        _reciprocal_subject(candidate, viewer),
    )


def _study_together(
    viewer: StudyDeclarations, candidate: StudyDeclarations
) -> DiscoveryMatch | None:
    first, second = viewer.active_goal, candidate.active_goal
    if first is None or second is None:
        return None
    subject_id = first.content.canonical_subject_id
    if (
        subject_id is None
        or subject_id != second.content.canonical_subject_id
        or not first.content.shared_learning
        or not second.content.shared_learning
    ):
        return None
    return DiscoveryMatch(
        RelevanceReason.SHARED_GOAL,
        subject_id,
        _same_topic(first.content.topic, second.content.topic),
        _reciprocal_subject(viewer, candidate),
    )


def discovery_match(
    viewer: StudyDeclarations,
    candidate: StudyDeclarations,
    mode: DiscoveryMode,
) -> DiscoveryMatch | None:
    if viewer.account_id == candidate.account_id:
        return None
    if mode == DiscoveryMode.FIND_HELP:
        return _find_help(viewer, candidate)
    if mode == DiscoveryMode.OFFER_HELP:
        return _offer_help(viewer, candidate)
    return _study_together(viewer, candidate)
