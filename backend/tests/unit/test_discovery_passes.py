from dataclasses import replace
from datetime import timedelta
from uuid import UUID

import pytest

from studymate.domain.discovery import DiscoveryMode
from studymate.domain.discovery_context import DiscoveryContext
from studymate.domain.discovery_passes import PrivatePassRevision
from tests.unit.test_discovery import NOW


def private_pass() -> PrivatePassRevision:
    return PrivatePassRevision(
        UUID(int=4),
        DiscoveryContext(UUID(int=1), DiscoveryMode.FIND_HELP, UUID(int=3), 1, None),
        UUID(int=2),
        1,
        True,
        7,
        NOW,
    )


def test_undo_is_latest_decision_scoped_without_a_decline_timer() -> None:
    revision = private_pass()
    assert revision.can_undo(7)
    assert not revision.can_undo(8)
    next_sequence = 9
    reconsidered = revision.reconsider(next_sequence, NOW + timedelta(days=2))
    assert not reconsidered.passed
    assert reconsidered.version == revision.version + 1
    assert reconsidered.decision_sequence == next_sequence
    assert not reconsidered.can_undo(9)
    assert revision.passed


def test_repeated_state_is_a_noop_and_repassing_is_a_new_retained_revision() -> None:
    revision = private_pass()
    assert revision.pass_again(8, NOW) is revision
    reconsidered = revision.reconsider(8, NOW)
    assert reconsidered.reconsider(9, NOW) is reconsidered
    again = reconsidered.pass_again(10, NOW)
    assert again.id == revision.id
    assert again.context == revision.context
    assert again.target_id == revision.target_id
    assert again.passed
    assert again.version == reconsidered.version + 1
    assert again.can_undo(10)
    assert not again.can_undo(11)


@pytest.mark.parametrize("sequence", [True, 0, 6, 7])
def test_new_state_needs_a_later_sequence(sequence: int) -> None:
    with pytest.raises(ValueError, match="later committed sequence"):
        private_pass().reconsider(sequence, NOW)


def test_revisions_reject_time_reversal_and_naive_timestamps() -> None:
    with pytest.raises(ValueError, match="precede"):
        private_pass().reconsider(8, NOW - timedelta(seconds=1))
    with pytest.raises(ValueError, match="timezone"):
        private_pass().reconsider(8, NOW.replace(tzinfo=None))


def test_invalid_private_source_facts_are_rejected() -> None:
    revision = private_pass()
    with pytest.raises(ValueError, match="target its owner"):
        replace(revision, target_id=revision.context.account_id)
    for value in (True, 0, -1):
        with pytest.raises(ValueError, match="positive"):
            replace(revision, version=value)
        with pytest.raises(ValueError, match="positive"):
            replace(revision, decision_sequence=value)
