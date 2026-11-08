from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from studymate.domain.discovery import (
    DiscoveryMode,
    RelevanceReason,
    StudyDeclarations,
    discovery_match,
    topic_match_key,
)
from studymate.domain.study_context import (
    CanonicalSubjectRef,
    CustomSubjectRef,
    GoalContent,
    HelpSubject,
    HelpSubjects,
    StudyGoal,
)

NOW = datetime(2026, 11, 7, tzinfo=UTC)
SUBJECT = UUID(int=3)
OTHER = UUID(int=4)


def test_literal_topic_keys_preserve_unicode_casefold_without_semantic_inference() -> None:
    assert topic_match_key("  Straße\tJOINs  ") == topic_match_key("STRASSE joins")
    assert topic_match_key("JOIN") != topic_match_key("SQL JOINs")
    assert topic_match_key(None) is None


def learner(account: int = 1, *, shared: bool = False) -> StudyDeclarations:
    account_id = UUID(int=account)
    return StudyDeclarations(
        account_id,
        StudyGoal(
            UUID(int=account + 10),
            account_id,
            1,
            GoalContent(
                CanonicalSubjectRef(SUBJECT), topic="Synthetic topic", shared_learning=shared
            ),
            NOW,
            NOW,
        ),
        HelpSubjects(),
    )


def helper() -> StudyDeclarations:
    return StudyDeclarations(
        UUID(int=2), None, HelpSubjects((HelpSubject(SUBJECT, " SYNTHETIC   topic "),))
    )


def test_find_help_requires_declared_subject_without_reciprocal_gate_or_role() -> None:
    found = discovery_match(learner(), helper(), DiscoveryMode.FIND_HELP)
    assert found is not None
    assert found.reason == RelevanceReason.CAN_HELP
    assert found.subject_id == SUBJECT
    assert found.same_topic
    assert found.reciprocal_subject_id is None
    assert (
        discovery_match(
            learner(), replace(helper(), help_subjects=HelpSubjects()), DiscoveryMode.FIND_HELP
        )
        is None
    )
    assert discovery_match(learner(), learner(), DiscoveryMode.FIND_HELP) is None


def test_offer_help_uses_candidate_goal_and_viewer_declaration_not_viewer_goal_role() -> None:
    found = discovery_match(helper(), learner(), DiscoveryMode.OFFER_HELP)
    assert found is not None
    assert found.reason == RelevanceReason.YOU_CAN_HELP
    assert found.same_topic
    assert discovery_match(learner(), helper(), DiscoveryMode.OFFER_HELP) is None


def test_subject_match_remains_truthful_when_topics_differ_or_are_missing() -> None:
    broad = replace(
        helper(), help_subjects=HelpSubjects((HelpSubject(SUBJECT, "Different topic"),))
    )
    match = discovery_match(learner(), broad, DiscoveryMode.FIND_HELP)
    assert match is not None
    assert not match.same_topic
    no_topic = replace(helper(), help_subjects=HelpSubjects((HelpSubject(SUBJECT),)))
    match = discovery_match(learner(), no_topic, DiscoveryMode.FIND_HELP)
    assert match is not None
    assert not match.same_topic


@pytest.mark.parametrize("mode", list(DiscoveryMode))
def test_custom_subject_never_becomes_exact_match_from_free_text(mode: DiscoveryMode) -> None:
    original = learner(shared=True)
    assert original.goal is not None
    custom = replace(
        original,
        goal=replace(
            original.goal,
            content=GoalContent(CustomSubjectRef("Synthetic topic"), shared_learning=True),
        ),
    )
    assert (
        discovery_match(
            custom, helper() if mode == DiscoveryMode.FIND_HELP else learner(2, shared=True), mode
        )
        is None
    )


def test_study_together_requires_both_explicit_shared_choices_and_same_active_subject() -> None:
    first, second = learner(shared=True), learner(2, shared=True)
    found = discovery_match(first, second, DiscoveryMode.STUDY_TOGETHER)
    assert found is not None
    assert found.reason == RelevanceReason.SHARED_GOAL
    assert found.same_topic
    assert discovery_match(learner(), second, DiscoveryMode.STUDY_TOGETHER) is None
    assert discovery_match(first, learner(2), DiscoveryMode.STUDY_TOGETHER) is None
    assert second.goal is not None
    completed = replace(second, goal=second.goal.complete(NOW))
    assert discovery_match(first, completed, DiscoveryMode.STUDY_TOGETHER) is None
    unrelated = replace(
        second,
        goal=replace(
            second.goal, content=GoalContent(CanonicalSubjectRef(OTHER), shared_learning=True)
        ),
    )
    assert discovery_match(first, unrelated, DiscoveryMode.STUDY_TOGETHER) is None
    assert discovery_match(replace(first, goal=None), second, DiscoveryMode.STUDY_TOGETHER) is None


def test_reciprocal_reason_requires_saved_counterpart_goal_and_viewer_help_subject() -> None:
    first = replace(learner(), help_subjects=HelpSubjects((HelpSubject(OTHER),)))
    second = helper()
    goal = StudyGoal(
        UUID(int=20), second.account_id, 1, GoalContent(CanonicalSubjectRef(OTHER)), NOW, NOW
    )
    second = replace(second, goal=goal)
    found = discovery_match(first, second, DiscoveryMode.FIND_HELP)
    assert found is not None
    assert found.reciprocal_subject_id == OTHER
    reverse = discovery_match(second, first, DiscoveryMode.OFFER_HELP)
    assert reverse is not None
    assert reverse.reciprocal_subject_id == OTHER
    assert (
        discovery_match(first, replace(second, goal=goal.complete(NOW)), DiscoveryMode.FIND_HELP)
        is not None
    )
    with pytest.raises(ValueError, match="belong"):
        replace(first, account_id=UUID(int=99))
