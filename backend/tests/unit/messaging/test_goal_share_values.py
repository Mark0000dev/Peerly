from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from studymate.domain.goal_shares import GoalShare, GoalShareState
from studymate.domain.relationships import AccountPair
from studymate.domain.study_context import CanonicalSubjectRef, GoalContent
from tests.unit.identity_store import NOW
from tests.unit.messaging.test_goal_shares import SENDER, saved_goal


def value() -> GoalShare:
    source = saved_goal(SENDER)
    return GoalShare(
        uuid4(),
        uuid4(),
        AccountPair.between(SENDER, UUID(int=3)),
        SENDER,
        1,
        source.goal,
        source.subject_label,
        NOW,
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda share: replace(share, owner_id=uuid4()),
        lambda share: replace(share, owner_id=share.pair.high),
        lambda share: replace(share, context_version=0),
        lambda share: replace(share, context_version=True),
        lambda share: replace(share, goal=share.goal.complete(NOW)),
        lambda share: replace(share, shared_at=NOW - timedelta(seconds=1)),
        lambda share: replace(share, subject_label="Invented source label"),
    ],
)
def test_shared_snapshot_rejects_fabricated_owner_time_revision_or_custom_source(
    mutation: Callable[[GoalShare], GoalShare],
) -> None:
    with pytest.raises(ValueError, match=r"participant|version|active|source"):
        mutation(value())


def test_explicit_canonical_and_custom_sources_do_not_require_discovery_sharing() -> None:
    custom = value()
    canonical = replace(
        custom,
        goal=replace(custom.goal, content=GoalContent(CanonicalSubjectRef(uuid4()))),
        subject_label="Actual retained canonical label",
    )
    assert not custom.goal.content.shared_learning
    assert not canonical.goal.content.shared_learning
    assert "Private" not in repr(custom)
    assert "Actual retained" not in repr(canonical)
    assert GoalShareState(0, None).latest is None
    assert GoalShareState(custom.context_version, custom).latest == custom


@pytest.mark.parametrize("version", [-1, True])
def test_context_zero_is_a_derived_baseline_not_a_fake_row(version: int) -> None:
    with pytest.raises(ValueError, match="nonnegative"):
        GoalShareState(version, None)


def test_context_head_requires_its_real_matching_shared_source() -> None:
    for version, latest in ((0, value()), (1, None), (2, value())):
        with pytest.raises(ValueError, match=r"baseline|source version"):
            GoalShareState(version, latest)
