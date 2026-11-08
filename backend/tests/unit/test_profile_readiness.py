from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from studymate.domain.identity import StudentEmail
from studymate.domain.membership import Membership
from studymate.domain.profile_readiness import (
    OnboardingRequirement,
    StudentProfileState,
    profile_capabilities,
)
from studymate.domain.profiles import DisplayName, OnboardingTask, ProfileBasics
from studymate.domain.study_context import (
    CanonicalSubjectRef,
    GoalContent,
    HelpSubject,
    HelpSubjects,
    StudyGoal,
)

NOW = datetime(2026, 11, 7, tzinfo=UTC)
ACCOUNT = UUID(int=1)
SUBJECT = UUID(int=2)
VERIFIED = Membership(StudentEmail("synthetic@mail.apu.edu.my"), NOW)


def ready() -> StudentProfileState:
    goal = StudyGoal(UUID(int=3), ACCOUNT, 1, GoalContent(CanonicalSubjectRef(SUBJECT)), NOW, NOW)
    return StudentProfileState(
        ACCOUNT,
        ProfileBasics(DisplayName("Synthetic student")),
        True,
        OnboardingTask.FIND_HELP,
        goal,
        HelpSubjects(),
    )


def test_first_task_is_not_a_role_or_forced_reciprocal_help() -> None:
    learner = ready()
    assert learner.initial_requirements == ()
    helper = replace(
        learner,
        task=OnboardingTask.OFFER_HELP,
        goal=None,
        help_subjects=HelpSubjects((HelpSubject(SUBJECT),)),
    )
    assert helper.initial_requirements == ()
    assert helper.has_study_context
    assert replace(helper, task=OnboardingTask.FIND_HELP).initial_requirements == (
        OnboardingRequirement.STUDY_GOAL,
    )
    assert replace(learner, task=OnboardingTask.OFFER_HELP).initial_requirements == (
        OnboardingRequirement.HELP_SUBJECTS,
    )


def test_draft_reports_actual_requirements_without_optional_profile_or_legal_steps() -> None:
    draft = replace(ready(), basics=ProfileBasics(), photo_ready=False, goal=None)
    assert draft.initial_requirements == (
        OnboardingRequirement.DISPLAY_NAME,
        OnboardingRequirement.PHOTO,
        OnboardingRequirement.STUDY_GOAL,
    )
    capabilities = profile_capabilities(
        membership=VERIFIED, banned=False, deleted=False, registered=False, profile=draft
    )
    assert capabilities.can_manage_profile
    assert not capabilities.can_complete_setup
    assert not capabilities.can_discover
    assert not capabilities.can_access_existing_chats


def test_usable_draft_still_needs_the_actual_explicit_registration_action() -> None:
    draft = ready()
    capabilities = profile_capabilities(
        membership=VERIFIED, banned=False, deleted=False, registered=False, profile=draft
    )
    assert capabilities.can_complete_setup
    assert capabilities.can_complete_registration
    assert not capabilities.identity.can_use_student_features
    assert not capabilities.can_discover
    registered = profile_capabilities(
        membership=VERIFIED, banned=False, deleted=False, registered=True, profile=draft
    )
    assert registered.can_complete_setup
    assert not registered.can_complete_registration


@pytest.mark.parametrize("state", ["hidden", "no_context", "photo_correction"])
def test_discovery_restrictions_keep_existing_chat_access_and_completion_history(
    state: str,
) -> None:
    profile = replace(ready(), completed_at=NOW)
    if state == "hidden":
        profile = replace(profile, hidden_at=NOW)
    elif state == "no_context":
        profile = replace(profile, goal=profile.goal.complete(NOW) if profile.goal else None)
    else:
        profile = replace(profile, photo_ready=False)
    capabilities = profile_capabilities(
        membership=VERIFIED, banned=False, deleted=False, registered=True, profile=profile
    )
    assert not capabilities.can_discover
    assert not capabilities.can_make_new_contacts
    assert capabilities.can_access_existing_chats
    assert capabilities.identity.can_use_student_features
    assert capabilities.can_manage_profile
    assert not capabilities.can_complete_setup
    assert capabilities.setup_requirements == ()


@pytest.mark.parametrize("restriction", ["unverified", "revoked", "banned", "deleted"])
def test_account_restrictions_never_grant_student_capabilities(restriction: str) -> None:
    membership = (
        None
        if restriction == "unverified"
        else replace(VERIFIED, revoked_at=NOW)
        if restriction == "revoked"
        else VERIFIED
    )
    capabilities = profile_capabilities(
        membership=membership,
        banned=restriction == "banned",
        deleted=restriction == "deleted",
        registered=True,
        profile=replace(ready(), completed_at=NOW),
    )
    assert not capabilities.can_manage_profile
    assert not capabilities.can_discover
    assert not capabilities.can_make_new_contacts
    assert not capabilities.can_access_existing_chats
    assert not capabilities.can_complete_registration


def test_normal_completed_account_can_discover_without_mandatory_help_declaration() -> None:
    capabilities = profile_capabilities(
        membership=VERIFIED,
        banned=False,
        deleted=False,
        registered=True,
        profile=replace(ready(), completed_at=NOW),
    )
    assert capabilities.can_discover
    assert capabilities.can_make_new_contacts
    assert capabilities.can_access_existing_chats


def test_projection_cannot_claim_another_accounts_goal_or_fake_completed_profile() -> None:
    with pytest.raises(ValueError, match="owner"):
        replace(ready(), account_id=UUID(int=99))
    with pytest.raises(ValueError, match="display name"):
        replace(ready(), basics=ProfileBasics(), completed_at=NOW)
    with pytest.raises(ValueError, match="timezone"):
        replace(ready(), hidden_at=NOW.replace(tzinfo=None))


def test_hidden_restore_uses_either_current_context_without_repeating_initial_task() -> None:
    hidden = replace(
        ready(),
        completed_at=NOW,
        hidden_at=NOW,
        goal=None,
        help_subjects=HelpSubjects((HelpSubject(SUBJECT),)),
    )
    capabilities = profile_capabilities(
        membership=VERIFIED, banned=False, deleted=False, registered=True, profile=hidden
    )
    assert capabilities.can_restore_profile
    assert not capabilities.can_hide_profile
    assert capabilities.restore_requirements == ()
    assert capabilities.can_access_existing_chats
    assert not capabilities.can_discover


def test_hidden_restore_reports_missing_photo_and_context_without_revoking_chat_access() -> None:
    hidden = replace(ready(), completed_at=NOW, hidden_at=NOW, photo_ready=False, goal=None)
    capabilities = profile_capabilities(
        membership=VERIFIED, banned=False, deleted=False, registered=True, profile=hidden
    )
    assert tuple(item.value for item in capabilities.restore_requirements) == (
        "photo",
        "study_context",
    )
    assert not capabilities.can_restore_profile
    assert capabilities.can_access_existing_chats
    assert capabilities.setup_requirements == ()
