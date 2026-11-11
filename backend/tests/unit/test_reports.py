from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from studymate.domain.reports import (
    MAX_REPORT_COMMENT_LENGTH,
    ProfileAccessContext,
    ProfileReport,
    ProfileVersionRefs,
    ReportCategory,
)

NOW = datetime(2026, 11, 7, tzinfo=UTC)
REPORTER = UUID(int=1)
TARGET = UUID(int=2)


def context() -> ProfileAccessContext:
    return ProfileAccessContext(
        UUID(int=3), REPORTER, ProfileVersionRefs(TARGET, 1, 1, None, None, None), NOW
    )


def report() -> ProfileReport:
    return ProfileReport(UUID(int=4), REPORTER, context(), ReportCategory.SPAM, NOW)


def test_selected_profile_is_referenced_without_copying_private_content_or_claiming_viewed() -> (
    None
):
    original = report()
    assert original.context.snapshot.account_id == TARGET
    assert original.comment is None
    detailed = replace(original, comment="  Private report\nselected context  ")
    assert detailed.comment == "Private report\nselected context"
    assert "Private report" not in repr(detailed)
    assert original.comment is None
    assert detailed.category == ReportCategory.SPAM


def test_other_requires_bounded_explanation_while_known_categories_do_not() -> None:
    with pytest.raises(ValueError, match="explanation"):
        replace(report(), category=ReportCategory.OTHER, comment="   ")
    assert replace(report(), category=ReportCategory.OTHER, comment="Synthetic explanation").comment
    with pytest.raises(ValueError, match="length"):
        replace(report(), comment="x" * (MAX_REPORT_COMMENT_LENGTH + 1))
    with pytest.raises(ValueError, match="Text"):
        replace(report(), comment="Private\x00content")


def test_retained_context_allows_later_report_but_never_another_reporter_or_a_self_target() -> None:
    original = report()
    later = replace(original, submitted_at=NOW + timedelta(days=365))
    assert later.context == original.context
    with pytest.raises(ValueError, match="another actor"):
        replace(original, reporter_id=TARGET)
    with pytest.raises(ValueError, match="target the viewer"):
        replace(context(), viewer_id=TARGET)
    with pytest.raises(ValueError, match="precede"):
        replace(original, submitted_at=NOW - timedelta(seconds=1))
    with pytest.raises(ValueError, match="timezone"):
        replace(original, submitted_at=NOW.replace(tzinfo=None))


@pytest.mark.parametrize("version", [0, -1, True])
def test_profile_context_revisions_cannot_be_invalid_or_unpaired(version: int) -> None:
    snapshot = context().snapshot
    with pytest.raises(ValueError, match="positive"):
        replace(snapshot, profile_version=version)
    with pytest.raises(ValueError, match="positive"):
        replace(snapshot, photo_version=version)
    with pytest.raises(ValueError, match="positive"):
        replace(snapshot, help_version=version)
    with pytest.raises(ValueError, match="positive"):
        replace(snapshot, goal_id=UUID(int=9), goal_version=version)
    with pytest.raises(ValueError, match="both"):
        replace(snapshot, goal_id=UUID(int=9))
    with pytest.raises(ValueError, match="both"):
        replace(snapshot, goal_version=1)
