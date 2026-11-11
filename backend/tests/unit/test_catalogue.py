from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from studymate.application.catalogue import CatalogueCursor, CatalogueQuery
from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import SessionCredential
from studymate.application.profiles.goals import CompleteGoalCommand, SaveGoalCommand
from studymate.domain.catalogue import MAX_SUBJECT_ALIASES, Subject, subject_key
from studymate.domain.study_context import CustomSubjectRef, GoalContent


def test_catalogue_normalizes_unicode_aliases_without_implied_equivalence() -> None:
    now = datetime.now(UTC)
    value = Subject(uuid4(), "  Synthetic   Straße  ", (" Other   Alias ",), now)
    assert value.name == "Synthetic Straße"
    assert value.aliases == ("Other Alias",)
    assert subject_key(value.name) == "synthetic strasse"
    assert value.selectable
    assert not replace(value, archived_at=now + timedelta(seconds=1)).selectable
    assert "Straße" not in repr(value)
    assert "Alias" not in repr(value)


@pytest.mark.parametrize(
    "aliases",
    [("SYNTHETIC",), ("Straße", "STRASSE"), tuple(str(i) for i in range(MAX_SUBJECT_ALIASES + 1))],
)
def test_aliases_are_bounded_and_casefold_distinct(aliases: tuple[str, ...]) -> None:
    with pytest.raises(ValueError, match="Subject aliases"):
        Subject(uuid4(), "Synthetic", aliases, datetime.now(UTC))


def test_catalogue_requires_aware_chronological_archive() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValueError, match="archival cannot"):
        Subject(uuid4(), "Synthetic", (), now, now - timedelta(seconds=1))
    with pytest.raises(ValueError, match="timezone"):
        Subject(uuid4(), "Synthetic", (), now, now.replace(tzinfo=None))


@pytest.mark.parametrize("version", [-1, True, 1])
def test_new_goal_expected_identity_and_revision_must_agree(version: int) -> None:
    with pytest.raises(ValueError, match="identity and revision"):
        SaveGoalCommand(
            SessionCredential("x" * 43),
            GoalContent(CustomSubjectRef("Synthetic")),
            None,
            version,
            IntentKey("test-operation"),
        )


@pytest.mark.parametrize("version", [-1, 0, True])
def test_goal_completion_requires_positive_nonboolean_revision(version: int) -> None:
    with pytest.raises(ValueError, match="revision must be positive"):
        CompleteGoalCommand(
            SessionCredential("x" * 43), uuid4(), version, IntentKey("test-operation")
        )


@pytest.mark.parametrize("limit", [0, -1, True, 51])
def test_catalogue_page_is_bounded(limit: int) -> None:
    with pytest.raises(ValueError, match="page size"):
        CatalogueQuery(limit=limit)


def test_catalogue_cursor_bounds() -> None:
    with pytest.raises(ValueError, match="cursor"):
        CatalogueCursor("", uuid4(), "")
