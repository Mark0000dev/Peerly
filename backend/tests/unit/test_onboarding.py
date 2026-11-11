from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from studymate.domain.media import PhotoRevision
from studymate.domain.onboarding import OnboardingActivation, ProfileLifecycle
from studymate.domain.profiles import DisplayName, OnboardingTask, ProfileBasics, ProfileRevision
from studymate.domain.registration import (
    PolicyKind,
    PolicyReference,
    PolicyVersion,
    RegistrationContext,
    RegistrationReceipt,
)
from studymate.domain.study_context import (
    CustomSubjectRef,
    GoalContent,
    HelpRevision,
    HelpSubject,
    HelpSubjects,
    StudyGoal,
)

NOW = datetime(2026, 11, 7, tzinfo=UTC)


def lifecycle() -> ProfileLifecycle:
    return ProfileLifecycle(UUID(int=1), NOW, 1, None, NOW)


def test_visibility_revisions_preserve_activation_and_do_not_invent_noop_history() -> None:
    initial = lifecycle()
    assert initial.with_visibility(hidden=False, at=NOW) is initial
    hidden = initial.with_visibility(hidden=True, at=NOW + timedelta(seconds=1))
    assert hidden.hidden
    assert hidden.visibility_version == initial.visibility_version + 1
    assert hidden.completed_at == initial.completed_at
    assert hidden.with_visibility(hidden=True, at=NOW + timedelta(seconds=2)) is hidden
    restored = hidden.with_visibility(hidden=False, at=NOW + timedelta(seconds=3))
    assert restored.visibility_version == hidden.visibility_version + 1
    assert restored.hidden_at is None
    assert initial.visibility_version == 1
    assert hidden.hidden_at == NOW + timedelta(seconds=1)


@pytest.mark.parametrize("version", [0, -1, True])
def test_visibility_revision_is_positive(version: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        replace(lifecycle(), visibility_version=version)


@pytest.mark.parametrize("hidden_at", [NOW - timedelta(seconds=1), NOW + timedelta(seconds=1)])
def test_hidden_timestamp_cannot_escape_recorded_history(hidden_at: datetime) -> None:
    with pytest.raises(ValueError, match="Hidden time"):
        replace(lifecycle(), hidden_at=hidden_at)


def test_visibility_history_cannot_be_reordered_even_for_noop_commands() -> None:
    with pytest.raises(ValueError, match="precede"):
        replace(lifecycle(), changed_at=NOW - timedelta(seconds=1))
    with pytest.raises(ValueError, match="precede"):
        lifecycle().with_visibility(hidden=False, at=NOW - timedelta(seconds=1))
    with pytest.raises(ValueError, match="timezone"):
        lifecycle().with_visibility(hidden=True, at=NOW.replace(tzinfo=None))


def activation() -> OnboardingActivation:
    account = UUID(int=1)
    context = RegistrationContext(
        UUID(int=2),
        account,
        UUID(int=3),
        PolicyReference(UUID(int=4), PolicyKind.TERMS, PolicyVersion("v1"), NOW),
        PolicyReference(UUID(int=5), PolicyKind.PRIVACY, PolicyVersion("v1"), NOW),
        "Synthetic registration notice",
        NOW,
        NOW + timedelta(minutes=10),
        NOW,
    )
    return OnboardingActivation(
        ProfileRevision(
            account, 1, ProfileBasics(DisplayName("Synthetic name")), OnboardingTask.FIND_HELP, NOW
        ),
        PhotoRevision(account, 1, UUID(int=6), NOW),
        StudyGoal(
            UUID(int=7), account, 1, GoalContent(CustomSubjectRef("Synthetic topic")), NOW, NOW
        ),
        None,
        RegistrationReceipt(UUID(int=8), account, context, NOW, "synthetic-key"),
        NOW,
    )


def test_activation_captures_actual_learner_or_helper_sources_without_optional_fields() -> None:
    learner = activation()
    assert learner.profile.basics.about is None
    helper = replace(
        learner,
        profile=replace(learner.profile, task=OnboardingTask.OFFER_HELP),
        goal=None,
        help_revision=HelpRevision(
            learner.profile.account_id, 1, HelpSubjects((HelpSubject(UUID(int=9)),)), NOW
        ),
    )
    assert helper.goal is None
    with pytest.raises(ValueError, match="chosen study context"):
        replace(helper, help_revision=None)
    with pytest.raises(ValueError, match="chosen study context"):
        replace(learner, goal=None)
    with pytest.raises(ValueError, match="chosen study context"):
        replace(learner, profile=replace(learner.profile, basics=ProfileBasics()))


@pytest.mark.parametrize("source", ["photo", "goal", "help", "registration"])
def test_activation_cannot_reference_another_accounts_sources(source: str) -> None:
    original = activation()
    foreign = UUID(int=99)
    photo, goal, help_revision, registration = (
        original.photo,
        original.goal,
        original.help_revision,
        original.registration,
    )
    if source == "photo":
        photo = replace(photo, account_id=foreign)
    elif source == "goal":
        assert goal is not None
        goal = replace(goal, account_id=foreign)
    elif source == "help":
        help_revision = HelpRevision(foreign, 1, HelpSubjects(), NOW)
    else:
        registration = replace(
            registration,
            account_id=foreign,
            context=replace(registration.context, account_id=foreign),
        )
    with pytest.raises(ValueError, match="one account"):
        replace(
            original, photo=photo, goal=goal, help_revision=help_revision, registration=registration
        )


def test_activation_cannot_precede_saved_sources_or_use_naive_time() -> None:
    with pytest.raises(ValueError, match="precede"):
        replace(activation(), completed_at=NOW - timedelta(seconds=1))
    with pytest.raises(ValueError, match="timezone"):
        replace(activation(), completed_at=NOW.replace(tzinfo=None))
