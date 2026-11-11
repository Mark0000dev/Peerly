from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from studymate.domain.profiles import DisplayName, LanguageCode, ProfileBasics
from studymate.domain.study_context import (
    CanonicalSubjectRef,
    CustomSubjectRef,
    GoalClosedError,
    GoalContent,
    HelpSubject,
    HelpSubjects,
    StudyGoal,
)

NOW = datetime(2026, 11, 7, tzinfo=UTC)
SUBJECT = CanonicalSubjectRef(UUID(int=3))


def goal() -> StudyGoal:
    return StudyGoal(UUID(int=1), UUID(int=2), 1, GoalContent(SUBJECT), NOW, NOW)


def test_subject_only_goal_is_usable_without_inferred_shared_learning_or_ability() -> None:
    content = GoalContent(SUBJECT, topic="   ")
    assert content.canonical_subject_id == SUBJECT.id
    assert content.topic is None
    assert not content.shared_learning
    custom = GoalContent(CustomSubjectRef("  Synthetic   custom topic  "))
    assert custom.canonical_subject_id is None
    assert isinstance(custom.subject, CustomSubjectRef)
    assert custom.subject.label == "Synthetic custom topic"
    assert "Synthetic" not in repr(custom)


def test_goal_revisions_and_completion_preserve_original_context() -> None:
    original = goal()
    content = GoalContent(
        SUBJECT, topic="Synthetic revision", context="Private context", shared_learning=True
    )
    revised = original.revise(content, NOW + timedelta(seconds=1))
    assert original.content.topic is None
    assert revised.id == original.id
    assert revised.version == original.version + 1
    assert revised.content == content
    assert revised.revise(content, NOW + timedelta(seconds=2)) is revised
    completed = revised.complete(NOW + timedelta(seconds=3))
    assert not completed.active
    assert revised.active
    assert completed.version == revised.version + 1
    assert completed.complete(NOW + timedelta(seconds=4)) is completed
    with pytest.raises(GoalClosedError):
        completed.revise(GoalContent(SUBJECT), NOW + timedelta(seconds=4))
    assert "Private context" not in repr(revised)


@pytest.mark.parametrize("version", [0, -1, True])
def test_goal_version_is_a_positive_integer(version: int) -> None:
    with pytest.raises(ValueError, match="version"):
        replace(goal(), version=version)


@pytest.mark.parametrize("at", [NOW.replace(tzinfo=None), NOW - timedelta(seconds=1)])
def test_goal_timestamps_cannot_reorder_or_use_naive_time(at: datetime) -> None:
    with pytest.raises(ValueError, match=r"timezone|precede"):
        goal().revise(GoalContent(SUBJECT), at)


def test_goal_completion_time_cannot_disagree_with_last_revision() -> None:
    with pytest.raises(ValueError, match="timestamp"):
        replace(goal(), completed_at=NOW + timedelta(seconds=1))


@pytest.mark.parametrize("text", ["x" * 81, "private\x00value", "private\nvalue", "\ud800"])
def test_invalid_topics_are_rejected_without_echoing_private_text(text: str) -> None:
    with pytest.raises(ValueError, match="Text") as failure:
        GoalContent(SUBJECT, topic=text)
    assert text not in str(failure.value)


def test_context_is_bounded_multiline_plain_text_and_helpers_are_independent() -> None:
    assert GoalContent(SUBJECT, context="  One\nTwo  ").context == "One\nTwo"
    assert HelpSubjects().values == ()
    assert (
        HelpSubjects((HelpSubject(SUBJECT.id, "  Synthetic note  "),)).values[0].topic_note
        == "Synthetic note"
    )
    with pytest.raises(ValueError, match="length"):
        GoalContent(SUBJECT, context="x" * 241)
    with pytest.raises(ValueError, match="distinct"):
        HelpSubjects((HelpSubject(SUBJECT.id), HelpSubject(SUBJECT.id)))
    with pytest.raises(ValueError, match="distinct"):
        HelpSubjects(tuple(HelpSubject(UUID(int=index)) for index in range(1, 7)))


def test_international_profile_text_is_normalized_without_optional_signup_gates() -> None:
    name = DisplayName("  أحمد   李  ")
    assert name.value == "أحمد 李"
    profile = ProfileBasics(name, about="  About\nme  ", languages=(LanguageCode(" EN "),))
    assert profile.about == "About\nme"
    assert profile.languages == (LanguageCode("en"),)
    assert profile.programme is None
    assert profile.year_label is None
    assert "أحمد" not in repr(profile)
    assert ProfileBasics(about=" ").about is None


@pytest.mark.parametrize("name", ["A", "x" * 51, "name\x00private", "\ud800x"])
def test_invalid_display_name_has_safe_validation(name: str) -> None:
    with pytest.raises(ValueError, match="Text") as failure:
        DisplayName(name)
    assert name not in str(failure.value)


@pytest.mark.parametrize(
    ("about", "programme", "year_label"),
    [("x" * 161, None, None), (None, "x" * 81, None), (None, None, "x" * 33)],
)
def test_optional_profile_fields_have_explicit_limits(
    about: str | None, programme: str | None, year_label: str | None
) -> None:
    with pytest.raises(ValueError, match="length"):
        ProfileBasics(about=about, programme=programme, year_label=year_label)


def test_language_choices_are_bounded_and_distinct_after_normalization() -> None:
    with pytest.raises(ValueError, match="distinct"):
        ProfileBasics(languages=(LanguageCode("en"), LanguageCode("EN")))
    with pytest.raises(ValueError, match="distinct"):
        ProfileBasics(
            languages=tuple(LanguageCode(value) for value in ("en", "ms", "zh", "ar", "ta", "hi"))
        )
    with pytest.raises(ValueError, match="selection key"):
        LanguageCode("not a selection")
