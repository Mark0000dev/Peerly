from dataclasses import replace
from uuid import UUID

import pytest

from studymate.domain.discovery import DiscoveryMode
from studymate.domain.discovery_context import DiscoveryContext, discovery_context
from studymate.domain.study_context import CustomSubjectRef, HelpRevision, HelpSubject, HelpSubjects
from tests.unit.test_discovery import NOW, SUBJECT, learner


def test_goal_edit_and_replacement_invalidate_private_decision_scope() -> None:
    actor = learner()
    goal = actor.goal
    assert goal is not None
    original = discovery_context(actor.account_id, DiscoveryMode.FIND_HELP, goal, None)
    assert original is not None
    assert original.goal_id == goal.id
    assert original.goal_version == goal.version
    changed = goal.revise(replace(goal.content, topic="A different topic"), NOW)
    assert discovery_context(actor.account_id, DiscoveryMode.FIND_HELP, changed, None) != original
    assert (
        discovery_context(
            actor.account_id, DiscoveryMode.FIND_HELP, replace(goal, id=UUID(int=99)), None
        )
        != original
    )


def test_offer_help_is_bound_to_help_revision_without_requiring_a_goal() -> None:
    actor = learner()
    help_revision = HelpRevision(actor.account_id, 1, HelpSubjects((HelpSubject(SUBJECT),)), NOW)
    original = discovery_context(actor.account_id, DiscoveryMode.OFFER_HELP, None, help_revision)
    assert original == DiscoveryContext(actor.account_id, DiscoveryMode.OFFER_HELP, None, None, 1)
    assert (
        discovery_context(actor.account_id, DiscoveryMode.OFFER_HELP, actor.goal, help_revision)
        == original
    )
    assert (
        discovery_context(
            actor.account_id, DiscoveryMode.OFFER_HELP, None, replace(help_revision, version=2)
        )
        != original
    )
    assert discovery_context(actor.account_id, DiscoveryMode.OFFER_HELP, actor.goal, None) is None
    assert (
        discovery_context(
            actor.account_id,
            DiscoveryMode.OFFER_HELP,
            None,
            replace(help_revision, subjects=HelpSubjects()),
        )
        is None
    )


def test_custom_completed_and_absent_goals_do_not_create_an_exact_match_scope() -> None:
    actor = learner()
    goal = actor.goal
    assert goal is not None
    custom = replace(goal, content=replace(goal.content, subject=CustomSubjectRef("SQL")))
    for value in (None, custom, goal.complete(NOW)):
        assert discovery_context(actor.account_id, DiscoveryMode.FIND_HELP, value, None) is None


def test_study_together_requires_explicit_choice_and_has_distinct_scope() -> None:
    actor = learner()
    goal = actor.goal
    assert goal is not None
    assert discovery_context(actor.account_id, DiscoveryMode.STUDY_TOGETHER, goal, None) is None
    shared = replace(goal, content=replace(goal.content, shared_learning=True))
    together = discovery_context(actor.account_id, DiscoveryMode.STUDY_TOGETHER, shared, None)
    assert together is not None
    assert together != discovery_context(actor.account_id, DiscoveryMode.FIND_HELP, shared, None)


def test_foreign_goal_or_help_revision_is_rejected_even_if_unused_in_mode() -> None:
    actor = learner()
    foreign = learner(2)
    with pytest.raises(ValueError, match="goal belongs"):
        discovery_context(actor.account_id, DiscoveryMode.OFFER_HELP, foreign.goal, None)
    help_revision = HelpRevision(foreign.account_id, 1, HelpSubjects(), NOW)
    with pytest.raises(ValueError, match="help declaration belongs"):
        discovery_context(actor.account_id, DiscoveryMode.FIND_HELP, actor.goal, help_revision)


@pytest.mark.parametrize("version", [None, 0, -1, True])
def test_invalid_context_revision_cannot_be_used_as_a_saved_scope(version: int | None) -> None:
    with pytest.raises(ValueError, match="positive saved revision"):
        DiscoveryContext(UUID(int=1), DiscoveryMode.FIND_HELP, UUID(int=2), version, None)


def test_context_cannot_mix_goal_and_help_sources() -> None:
    for mode in DiscoveryMode:
        with pytest.raises(ValueError, match="context uses"):
            DiscoveryContext(UUID(int=1), mode, UUID(int=2), 1, 1)
