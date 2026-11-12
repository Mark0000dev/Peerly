from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from deployment.backend.external_delivery_activation import (
    ActivationRejectedError,
    Registered,
    Schedule,
    Snapshot,
    SupportTarget,
    Targets,
    UmamiTarget,
    build_plan,
    registrations,
    require_snapshot,
    target_states,
    validate_plan,
)
from pydantic import ValidationError

NOW = datetime(2026, 11, 12, tzinfo=UTC)


@pytest.fixture
def targets() -> Targets:
    return Targets(
        schema_version=1,
        database="peerly_staging",
        database_schema="public",
        migration_revision="0060_report_triage",
        backend_image="ghcr.io/mark0000dev/peerly-backend@sha256:" + "a" * 64,
        support_notice_not_before=NOW - timedelta(minutes=1),
        umami=UmamiTarget(
            revision=1, origin="https://analytics.example.test", website_id=UUID(int=1)
        ),
        telegram_support=SupportTarget(
            revision=1,
            chat_id=-100123456,
            operator_origin="https://peerly-staging.example.test",
            topic_id=None,
        ),
    )


@pytest.fixture
def snapshot() -> Snapshot:
    return Snapshot(
        captured_at=NOW,
        registered=(),
        schedules=(
            Schedule(sink="umami", turn=0, blocked=False, cooldown_until=None),
            Schedule(sink="telegram_support", turn=1, blocked=False, cooldown_until=None),
        ),
        capture_triggers_verified=True,
        unsettled_deliveries=0,
        unresolved_attempts=0,
        pending_other_revision=0,
        old_support_notices=0,
        pending_sources=142,
    )


def test_new_targets_can_be_planned_but_are_not_registered(
    targets: Targets, snapshot: Snapshot
) -> None:
    plan = build_plan(targets, snapshot)
    validate_plan(plan, NOW)
    assert target_states(targets, snapshot) == ("new", "new")
    with pytest.raises(ActivationRejectedError, match="target_registration_required"):
        require_snapshot(targets, snapshot, registered=True)


def test_existing_exact_targets_are_idempotent_matches(
    targets: Targets, snapshot: Snapshot
) -> None:
    rows = tuple(
        Registered(
            sink="umami" if item.destination.sink.value == "umami" else "telegram_support",
            revision=item.destination.revision,
            fingerprint=item.fingerprint.hex(),
            registered_at=NOW,
        )
        for item in registrations(targets)
    )
    current = snapshot.model_copy(update={"registered": rows})
    require_snapshot(targets, current, registered=True)
    assert target_states(targets, current) == ("matching", "matching")


@pytest.mark.parametrize(
    "field",
    [
        "unsettled_deliveries",
        "unresolved_attempts",
        "pending_other_revision",
        "old_support_notices",
    ],
)
def test_unreviewed_work_is_not_cleared_to_register(
    targets: Targets, snapshot: Snapshot, field: str
) -> None:
    changed = snapshot.model_copy(update={field: 1})
    with pytest.raises(ActivationRejectedError):
        require_snapshot(targets, changed, registered=False)


def test_approved_snapshot_cannot_be_retimed_without_breaking_plan_hash(
    targets: Targets, snapshot: Snapshot
) -> None:
    plan = build_plan(targets, snapshot)
    changed = plan.model_copy(
        update={
            "snapshot": snapshot.model_copy(update={"captured_at": NOW + timedelta(minutes=10)})
        }
    )
    with pytest.raises(ActivationRejectedError, match="fingerprint"):
        validate_plan(changed, NOW + timedelta(minutes=10))


def test_stale_approved_plan_is_not_reused_as_fresh_state(
    targets: Targets, snapshot: Snapshot
) -> None:
    with pytest.raises(ActivationRejectedError, match="stale_or_future"):
        validate_plan(build_plan(targets, snapshot), NOW + timedelta(minutes=6))


def test_changed_target_is_not_rebound_to_an_existing_revision(
    targets: Targets, snapshot: Snapshot
) -> None:
    existing = Registered(sink="umami", revision=1, fingerprint="0" * 64, registered_at=NOW)
    with pytest.raises(ActivationRejectedError, match="registered_target_mismatch"):
        require_snapshot(
            targets, snapshot.model_copy(update={"registered": (existing,)}), registered=False
        )


def test_product_support_config_has_no_token_or_technical_sink_field(targets: Targets) -> None:
    with pytest.raises(ValidationError):
        Targets.model_validate_json(targets.model_dump_json()[:-1] + ',"telegram_dev":{}}')
    assert set(SupportTarget.model_fields) == {"revision", "chat_id", "operator_origin", "topic_id"}


def test_disabled_capture_or_blocked_sink_never_becomes_readiness(
    targets: Targets, snapshot: Snapshot
) -> None:
    for changed in (
        snapshot.model_copy(update={"capture_triggers_verified": False}),
        snapshot.model_copy(
            update={
                "schedules": (
                    snapshot.schedules[0].model_copy(update={"blocked": True}),
                    snapshot.schedules[1],
                )
            }
        ),
    ):
        with pytest.raises(ActivationRejectedError):
            require_snapshot(targets, changed, registered=False)
