from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from deployment.backend.external_delivery_activation import (
    TARGETS_CODEC,
    ActivationRejectedError,
    DeferredSupport,
    Plan,
    Registered,
    Schedule,
    Snapshot,
    UmamiOnlyTargets,
    UmamiTarget,
    build_plan,
    read_model,
    registrations,
    require_snapshot,
    target_states,
    validate_plan,
)
from pydantic import SecretStr, ValidationError

from studymate.bootstrap import _ConfiguredExternalDestinations, _external_destination_configs
from studymate.config import ExternalDeliveryWorkerSettings, UmamiDeliveryConfiguration
from studymate.domain.external_delivery.sources import Sink

NOW = datetime(2026, 11, 13, tzinfo=UTC)


@pytest.fixture
def umami_targets() -> UmamiOnlyTargets:
    return UmamiOnlyTargets(
        schema_version=2,
        mode="umami_only",
        database="peerly_staging",
        database_schema="public",
        migration_revision="0060_report_triage",
        backend_image="ghcr.io/mark0000dev/peerly-backend@sha256:" + "a" * 64,
        umami=UmamiTarget(
            revision=1, origin="https://analytics.example.test", website_id=UUID(int=1)
        ),
    )


@pytest.fixture
def partial_snapshot() -> Snapshot:
    return Snapshot(
        captured_at=NOW,
        registered=(),
        schedules=(
            Schedule(sink="umami", turn=0, blocked=False, cooldown_until=None),
            Schedule(
                sink="telegram_support",
                turn=1,
                blocked=True,
                cooldown_until=NOW + timedelta(hours=1),
            ),
        ),
        capture_triggers_verified=True,
        unsettled_deliveries=0,
        unresolved_attempts=0,
        pending_other_revision=0,
        old_support_notices=None,
        pending_sources=2,
        deferred_support=DeferredSupport(
            sources_pending=2,
            pending_unbound=3,
            pending_bound=0,
            unsettled_deliveries=0,
            unresolved_attempts=0,
            registered_destinations=0,
            attempts_total=0,
            succeeded_deliveries=0,
        ),
    )


def test_partial_plan_is_exactly_one_sink_and_roundtrips_closed_schema(
    umami_targets: UmamiOnlyTargets,
    partial_snapshot: Snapshot,
) -> None:
    parsed = TARGETS_CODEC.validate_json(umami_targets.model_dump_json())
    assert isinstance(parsed, UmamiOnlyTargets)
    items = registrations(parsed)
    assert len(items) == 1
    assert items[0].destination.sink == Sink.UMAMI
    plan = Plan.model_validate_json(build_plan(parsed, partial_snapshot).model_dump_json())
    validate_plan(plan, NOW)
    assert target_states(plan.targets, plan.snapshot) == ("new",)
    assert "telegram_support" not in plan.targets.model_dump()
    assert "support_notice_not_before" not in plan.targets.model_dump()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("telegram_support", None),
        ("support_notice_not_before", NOW.isoformat()),
        ("token", "PRIVATE_TOKEN_CANARY"),
        ("mode", "both"),
        ("mode", "umami-and-later"),
    ],
)
def test_partial_manifest_cannot_smuggle_dummy_support_or_credentials(
    umami_targets: UmamiOnlyTargets,
    field: str,
    value: object,
) -> None:
    data = umami_targets.model_dump()
    assert TARGETS_CODEC.validate_python(data) == umami_targets
    data[field] = value
    with pytest.raises(ValidationError):
        TARGETS_CODEC.validate_python(data)


def test_omitted_support_state_remains_visible_without_becoming_activation_authority(
    umami_targets: UmamiOnlyTargets,
    partial_snapshot: Snapshot,
) -> None:
    require_snapshot(umami_targets, partial_snapshot, registered=False)
    assert partial_snapshot.deferred_support is not None
    assert partial_snapshot.deferred_support.pending_unbound > 0
    assert partial_snapshot.old_support_notices is None
    with pytest.raises(ActivationRejectedError, match="registration_required"):
        require_snapshot(umami_targets, partial_snapshot, registered=True)
    item = registrations(umami_targets)[0]
    matching = partial_snapshot.model_copy(
        update={
            "registered": (
                Registered(
                    sink="umami",
                    revision=item.destination.revision,
                    fingerprint=item.fingerprint.hex(),
                    registered_at=NOW,
                ),
            )
        }
    )
    require_snapshot(umami_targets, matching, registered=True)
    assert target_states(umami_targets, matching) == ("matching",)


@pytest.mark.parametrize(
    "field", ["unsettled_deliveries", "unresolved_attempts", "pending_other_revision"]
)
def test_partial_mode_cannot_bypass_selected_sink_work_review(
    umami_targets: UmamiOnlyTargets,
    partial_snapshot: Snapshot,
    field: str,
) -> None:
    with pytest.raises(ActivationRejectedError, match="requires_review"):
        require_snapshot(
            umami_targets, partial_snapshot.model_copy(update={field: 1}), registered=False
        )


def test_partial_mode_cannot_fabricate_support_cutoff_or_hide_inventory(
    umami_targets: UmamiOnlyTargets,
    partial_snapshot: Snapshot,
) -> None:
    for snapshot in (
        partial_snapshot.model_copy(update={"old_support_notices": 0}),
        partial_snapshot.model_copy(update={"deferred_support": None}),
    ):
        with pytest.raises(ActivationRejectedError, match="deferred_support_inventory_required"):
            require_snapshot(umami_targets, snapshot, registered=False)


def test_mode_specific_approval_remains_fresh_and_immutable(
    umami_targets: UmamiOnlyTargets,
    partial_snapshot: Snapshot,
) -> None:
    plan = build_plan(umami_targets, partial_snapshot)
    with pytest.raises(ActivationRejectedError, match="stale_or_future"):
        validate_plan(plan, NOW + timedelta(minutes=6))
    changed = plan.model_copy(
        update={
            "targets": umami_targets.model_copy(
                update={
                    "umami": umami_targets.umami.model_copy(update={"revision": 2}),
                }
            )
        }
    )
    with pytest.raises(ActivationRejectedError, match="fingerprint"):
        validate_plan(changed, NOW)


def test_private_manifest_reader_dispatches_schema_without_support_placeholder(
    tmp_path: Path,
    umami_targets: UmamiOnlyTargets,
) -> None:
    path = tmp_path / "target.json"
    path.write_text(umami_targets.model_dump_json())
    path.chmod(0o600)
    assert read_model(path, plan=False) == umami_targets


def test_real_existing_worker_configuration_skips_support_without_a_dummy_target() -> None:
    settings = ExternalDeliveryWorkerSettings(
        _env_file=None,
        database_url=SecretStr("postgresql+asyncpg://test:synthetic@localhost/owned_test"),
        observability=None,
        telegram_support=None,
        umami=UmamiDeliveryConfiguration(
            hostname="app.example.test",
            revision=1,
            origin="https://analytics.example.test",
            website_id=UUID(int=1),
        ),
    )
    configurations = _external_destination_configs(settings)
    registry = _ConfiguredExternalDestinations(tuple(value.destination for value in configurations))
    assert settings.telegram_support is None
    assert len(configurations) == 1
    assert registry.destination(Sink.TELEGRAM_SUPPORT) is None
    assert registry.destination(Sink.UMAMI) is not None
