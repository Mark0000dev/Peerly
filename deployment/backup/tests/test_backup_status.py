import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from deployment.backup import backup_status as status

NOW = datetime(2026, 11, 13, 12, tzinfo=UTC)
RUN = "20261113T120000Z-" + "a" * 32
METADATA_MODE = 0o644
EXAMPLE_FRESHNESS_SECONDS = 108000
PRIVATE = "SYNTHETIC_PRIVATE_NOT_IN_METRICS"


def write(path: Path, data: dict[str, object]) -> None:
    path.write_text(json.dumps(data))
    path.chmod(0o600)


def fixture(root: Path, *, success: bool = True) -> None:
    root.mkdir(mode=0o700)
    verified = (NOW - timedelta(minutes=1)).isoformat()
    write(
        root / "last-result.json",
        {
            "attempt_at": NOW.isoformat(),
            "success": success,
            "last_verified_at": verified,
            "full_restore_proven": False,
        },
    )
    write(root / "last-verified.json", {"verified_at": verified, "run_id": RUN})
    (root / "catalog").mkdir(mode=0o700)
    write(
        root / "catalog" / (RUN + ".json"),
        {
            "run_id": RUN,
            "verified_at": verified,
            "encrypted_remote_readback_verified": True,
            "plaintext_readback_tree_created": False,
            "readback_mode": "native_sha256_download",
            "full_restore_proven": False,
        },
    )


def test_verified_state_requires_real_catalog_and_has_no_private_labels(tmp_path: Path) -> None:
    root = tmp_path / "state"
    fixture(root)
    values = status.snapshot(root, "success", NOW)
    assert values["status_valid"] == 1
    assert values["last_attempt_success"] == 1
    assert values["last_verified_timestamp_seconds"] > 0
    assert values["unit_success"] == 1
    rendered = status.render(values)
    assert RUN.encode() not in rendered
    assert str(root).encode() not in rendered
    assert b"{" not in rendered
    (root / "catalog" / (RUN + ".json")).unlink()
    assert status.snapshot(root, "success", NOW)["status_valid"] == 0


def test_unit_start_failure_is_visible_without_credentials_or_state(tmp_path: Path) -> None:
    values = status.snapshot(tmp_path / "missing", "resources", NOW)
    assert values["status_valid"] == 0
    assert values["unit_result_known"] == 1
    assert values["unit_success"] == 0
    assert values["last_verified_timestamp_seconds"] == 0


def test_failed_attempt_retains_last_verified_timestamp(tmp_path: Path) -> None:
    root = tmp_path / "state"
    fixture(root, success=False)
    values = status.snapshot(root, "exit-code", NOW)
    assert values["status_valid"] == 1
    assert values["last_attempt_success"] == 0
    assert values["last_verified_timestamp_seconds"] == (NOW - timedelta(minutes=1)).timestamp()
    assert values["unit_result_known"] == 1
    assert values["unit_success"] == 0


@pytest.mark.parametrize("change", ["corrupt", "symlink", "future", "inconsistent", "unverified"])
def test_invalid_metadata_never_looks_healthy(tmp_path: Path, change: str) -> None:
    root = tmp_path / "state"
    fixture(root)
    path = root / "last-result.json"
    if change == "corrupt":
        path.write_text(PRIVATE)
    elif change == "symlink":
        path.unlink()
        path.symlink_to(tmp_path / "not-a-status")
    else:
        record = json.loads(path.read_text())
        if change == "future":
            record["attempt_at"] = (NOW + timedelta(days=1)).isoformat()
        elif change == "inconsistent":
            record["attempt_at"] = (NOW - timedelta(hours=1)).isoformat()
        else:
            record["last_verified_at"] = None
        write(path, record)
    values = status.snapshot(root, "unknown", NOW)
    assert values["status_valid"] == 0
    assert values["last_attempt_success"] == 0
    assert values["unit_result_known"] == 0
    assert PRIVATE.encode() not in status.render(values)


def test_atomic_metrics_are_readable_metadata_only_and_reject_symlink(tmp_path: Path) -> None:
    tmp_path.chmod(0o755)
    output = tmp_path / "backup.prom"
    data = status.render(status.snapshot(tmp_path / "missing", "unknown", NOW))
    status.publish(output, data)
    assert output.read_bytes() == data
    assert output.stat().st_mode & 0o777 == METADATA_MODE
    assert not list(tmp_path.glob(".backup-*"))
    output.unlink()
    output.symlink_to(tmp_path / "outside")
    with pytest.raises(status.StatusError, match="metrics_destination"):
        status.publish(output, data)


def test_status_rejects_unsafe_unit_value_and_timezone() -> None:
    with pytest.raises(status.StatusError, match="unit_result"):
        status.snapshot(Path("/not-read"), PRIVATE, NOW)
    with pytest.raises(status.StatusError, match="unit_result"):
        status.snapshot(Path("/not-read"), "success", NOW.replace(tzinfo=None))


def test_stale_receipt_keeps_its_real_age_instead_of_refreshing_success(tmp_path: Path) -> None:
    root = tmp_path / "state"
    fixture(root)
    later = NOW + timedelta(days=4)
    values = status.snapshot(root, "success", later)
    assert values["status_valid"] == 1
    assert values["last_verified_timestamp_seconds"] == (NOW - timedelta(minutes=1)).timestamp()
    assert later.timestamp() - values["last_verified_timestamp_seconds"] > EXAMPLE_FRESHNESS_SECONDS


@pytest.mark.parametrize("change", ["state-link", "catalog-link", "public-json", "duplicate-json"])
def test_nofollow_and_private_metadata_boundaries(tmp_path: Path, change: str) -> None:
    root = tmp_path / "state"
    fixture(root)
    if change == "state-link":
        actual = tmp_path / "actual"
        root.rename(actual)
        root.symlink_to(actual, target_is_directory=True)
    elif change == "catalog-link":
        (root / "catalog").rename(root / "actual-catalog")
        (root / "catalog").symlink_to(root / "actual-catalog", target_is_directory=True)
    elif change == "public-json":
        (root / "last-result.json").chmod(0o644)
    else:
        (root / "last-result.json").write_text('{"success":true,"success":false}')
    assert status.snapshot(root, "success", NOW)["status_valid"] == 0


def test_real_producer_status_writer_accepts_distinct_catalog_timestamp(tmp_path: Path) -> None:
    from deployment.backup import run_backup as producer
    from deployment.backup.retention import Retention

    root = tmp_path / "state"
    fixture(root)
    actual_now = datetime.now(UTC)
    committed = json.loads((root / "catalog" / (RUN + ".json")).read_text())
    committed["verified_at"] = (actual_now - timedelta(seconds=30)).isoformat()
    write(root / "catalog" / (RUN + ".json"), committed)
    plan = producer.Plan(
        root,
        "a" * 64,
        Path("/synthetic/rclone"),
        "b" * 64,
        "business-key-0001",
        "drill-0001",
        3758096384,
        Retention(14, 8, 12),
    )
    producer.result_status(plan, True, RUN)
    values = status.snapshot(root, "success", datetime.now(UTC))
    assert values["status_valid"] == 1
    assert values["last_attempt_success"] == 1


def test_failed_atomic_replace_preserves_previous_sample(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    output = tmp_path / "backup.prom"
    output.write_bytes(b"previous numeric sample\n")

    def fail_replace(source: str, target: str, *, src_dir_fd: int, dst_dir_fd: int) -> None:
        del source, target, src_dir_fd, dst_dir_fd
        raise OSError("synthetic local failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="synthetic local failure"):
        status.publish(output, b"new sample\n")
    assert output.read_bytes() == b"previous numeric sample\n"
    assert not list(tmp_path.glob(".backup-*"))
