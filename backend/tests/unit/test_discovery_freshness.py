from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from studymate.domain.discovery_freshness import (
    DiscoveryExposure,
    DiscoveryFreshnessPolicy,
    ExposureConfirmation,
)

NOW = datetime(2026, 11, 7, tzinfo=UTC)
POLICY = DiscoveryFreshnessPolicy()


def exposure() -> DiscoveryExposure:
    return DiscoveryExposure(UUID(int=1), NOW, NOW)


def test_inactivity_is_exposure_only_and_reads_do_not_warm_foreground_activity() -> None:
    initial = exposure()
    deadline = NOW + POLICY.inactivity
    assert initial.effective_pause(deadline - timedelta(microseconds=1)) is None
    assert initial.effective_pause(deadline) == deadline
    assert initial.effective_pause(deadline + timedelta(days=1)) == deadline
    assert initial.last_activity_at == NOW
    assert initial.confirmed_at == NOW
    assert initial.paused_at is None


def test_first_return_materializes_pause_before_warming_activity() -> None:
    initial = exposure()
    returned_at = NOW + POLICY.inactivity + timedelta(days=1)
    returned = initial.record_foreground_activity(returned_at, POLICY)
    assert returned.last_activity_at == returned_at
    assert returned.confirmed_at == NOW
    assert returned.paused_at == NOW + POLICY.inactivity
    later = returned.record_foreground_activity(returned_at + timedelta(hours=1), POLICY)
    assert later.paused_at == returned.paused_at
    assert later.effective_pause(later.last_activity_at) == returned.paused_at
    assert returned.record_foreground_activity(returned_at, POLICY) is returned


def test_explicit_confirmation_records_source_and_starts_new_window() -> None:
    initial = exposure()
    at = NOW + POLICY.inactivity
    confirmed, fact = initial.confirm_exposure(at, POLICY)
    assert fact == ExposureConfirmation(initial.account_id, at, at)
    assert confirmed.confirmed_at == at
    assert confirmed.last_activity_at == at
    assert confirmed.paused_at is None
    assert confirmed.effective_pause(at) is None
    assert confirmed.effective_pause(at + POLICY.inactivity) == at + POLICY.inactivity
    assert initial.confirmed_at == NOW
    assert initial.last_activity_at == NOW


def test_already_fresh_confirmation_does_not_fabricate_another_confirmation_fact() -> None:
    initial = exposure()
    unchanged, fact = initial.confirm_exposure(NOW, POLICY)
    assert unchanged is initial
    assert fact is None
    later, fact = initial.confirm_exposure(NOW + timedelta(hours=1), POLICY)
    assert later.confirmed_at == initial.confirmed_at
    assert fact is None


def test_configured_interval_is_a_policy_value_not_a_public_lifecycle_state() -> None:
    policy = DiscoveryFreshnessPolicy(timedelta(days=2))
    assert (
        replace(exposure(), inactivity=policy.inactivity).effective_pause(NOW + timedelta(days=2))
        is not None
    )
    with pytest.raises(ValueError, match="positive"):
        DiscoveryFreshnessPolicy(timedelta())


def test_invalid_time_order_and_naive_time_never_reset_source_facts() -> None:
    initial = exposure()
    with pytest.raises(ValueError, match="precede"):
        replace(initial, last_activity_at=NOW - timedelta(seconds=1))
    with pytest.raises(ValueError, match="precede"):
        replace(initial, paused_at=NOW - timedelta(seconds=1))
    with pytest.raises(ValueError, match="precede"):
        initial.record_foreground_activity(NOW - timedelta(seconds=1), POLICY)
    with pytest.raises(ValueError, match="precede"):
        replace(initial, paused_at=NOW + timedelta(days=1)).effective_pause(NOW)
    with pytest.raises(ValueError, match="precede"):
        ExposureConfirmation(initial.account_id, NOW, NOW + timedelta(seconds=1))
    with pytest.raises(ValueError, match="timezone"):
        initial.confirm_exposure(NOW.replace(tzinfo=None), POLICY)


def test_new_policy_cannot_reopen_an_already_expired_activity_source() -> None:
    initial = exposure()
    at = NOW + POLICY.inactivity + timedelta(days=1)
    longer = DiscoveryFreshnessPolicy(timedelta(days=60))
    returned = initial.record_foreground_activity(at, longer)
    assert returned.inactivity == longer.inactivity
    assert returned.paused_at == NOW + POLICY.inactivity
    assert returned.effective_pause(at) == returned.paused_at
    confirmed, fact = returned.confirm_exposure(at, longer)
    assert fact is not None
    assert confirmed.effective_pause(at + longer.inactivity) == at + longer.inactivity


def test_new_foreground_activity_applies_current_interval_without_rewriting_older_facts() -> None:
    shorter = DiscoveryFreshnessPolicy(timedelta(days=2))
    at = NOW + timedelta(days=1)
    updated = exposure().record_foreground_activity(at, shorter)
    assert updated.inactivity == shorter.inactivity
    assert updated.effective_pause(at + shorter.inactivity) == at + shorter.inactivity
    with pytest.raises(ValueError, match="positive"):
        replace(updated, inactivity=timedelta())
