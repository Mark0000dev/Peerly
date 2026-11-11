from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from studymate.domain.relationships import AccountPair, BlockRevision, pair_is_blocked

NOW = datetime(2026, 11, 7, tzinfo=UTC)
FIRST = UUID(int=1)
SECOND = UUID(int=2)
PAIR = AccountPair.between(FIRST, SECOND)


def revision() -> BlockRevision:
    return BlockRevision(UUID(int=3), PAIR, FIRST, 1, True, NOW)


def test_pair_order_is_canonical_and_does_not_depend_on_command_direction() -> None:
    assert AccountPair.between(FIRST, SECOND) == AccountPair.between(SECOND, FIRST)
    assert PAIR.counterpart(FIRST) == SECOND
    assert PAIR.counterpart(SECOND) == FIRST
    with pytest.raises(ValueError, match="distinct"):
        AccountPair.between(FIRST, FIRST)
    with pytest.raises(ValueError, match="ordered"):
        AccountPair(SECOND, FIRST)
    with pytest.raises(ValueError, match="participant"):
        PAIR.counterpart(UUID(int=99))


def test_block_ownership_and_revisions_preserve_each_participants_independent_decision() -> None:
    first = revision()
    second = replace(first, blocker_id=SECOND)
    assert first.target_id == SECOND
    assert second.target_id == FIRST
    assert pair_is_blocked(first, second)
    unblocked = first.change(actor_id=FIRST, blocked=False, at=NOW + timedelta(seconds=1))
    assert unblocked.version == first.version + 1
    assert pair_is_blocked(unblocked, second)
    assert not pair_is_blocked(unblocked, second.change(actor_id=SECOND, blocked=False, at=NOW))
    assert first.blocked
    assert first.change(actor_id=FIRST, blocked=True, at=NOW) is first
    with pytest.raises(ValueError, match="Only the blocker"):
        first.change(actor_id=SECOND, blocked=False, at=NOW)


def test_absent_blocks_are_not_hidden_interest_or_a_connection() -> None:
    assert not pair_is_blocked(None, None)
    assert pair_is_blocked(revision(), None)
    assert pair_is_blocked(None, revision())
    assert not pair_is_blocked(replace(revision(), blocked=False), None)


@pytest.mark.parametrize("version", [0, -1, True])
def test_block_revision_is_positive(version: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        replace(revision(), version=version)


def test_block_cannot_be_forged_for_another_pair_or_reorder_time() -> None:
    first = revision()
    with pytest.raises(ValueError, match="participant"):
        replace(first, blocker_id=UUID(int=99))
    with pytest.raises(ValueError, match="precede"):
        first.change(actor_id=FIRST, blocked=False, at=NOW - timedelta(seconds=1))
    with pytest.raises(ValueError, match="timezone"):
        replace(first, changed_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="opposite sides"):
        pair_is_blocked(first, first)
    with pytest.raises(ValueError, match="same pair"):
        pair_is_blocked(first, replace(first, blocker_id=SECOND, relationship_id=UUID(int=99)))
    with pytest.raises(ValueError, match="same pair"):
        pair_is_blocked(
            first,
            replace(first, pair=AccountPair.between(FIRST, UUID(int=99)), blocker_id=UUID(int=99)),
        )
