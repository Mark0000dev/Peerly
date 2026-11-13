import hashlib
import json
import os
from pathlib import Path

import pytest
from deployment.backup import install_backup as install

CODE = Path(install.__file__).parents[2]


def test_exact_runtime_closure_and_inactive_units(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    checksum = install.prepare(CODE, bundle)
    contents = install.closure(bundle, checksum)
    assert set(contents) == install.FILES
    assert "deployment/restore/recovery_and.py" in contents
    release = Path("/usr/local/lib/peerly-backup/releases") / checksum
    units = install.render_units(contents, release, Path("/usr/bin/python3"), False)
    primary, failure = units["peerly-backup.service"], units["peerly-backup-failed.service"]
    assert b"OnFailure=peerly-backup-failed.service" in primary
    assert b"ExecStopPost=" in primary
    assert b"LoadCredential" not in failure
    assert b"MemoryMax=512M" in primary
    assert b"CPUQuota=50%" in primary
    assert b"TasksMax=64" in primary
    assert b"@@" not in b"".join(units.values())
    assert b"LoadCredential=pg-ca:" not in primary
    with_ca = install.render_units(contents, release, Path("/usr/bin/python3"), True)
    assert b"LoadCredential=pg-ca:" in with_ca["peerly-backup.service"]
    assert not any((tmp_path / name).exists() for name in units)


def test_manifest_and_source_tamper_are_closed(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    checksum = install.prepare(CODE, bundle)
    with pytest.raises(install.InstallError, match="manifest_pin"):
        install.closure(bundle, "0" * 64)
    (bundle / "deployment/restore/acceptance.sql").write_text("tampered")
    with pytest.raises(install.InstallError, match="source_pin"):
        install.closure(bundle, checksum)


def test_missing_required_module_cannot_be_omitted_from_manifest(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    install.prepare(CODE, bundle)
    manifest = json.loads((bundle / "manifest.json").read_text())
    del manifest["files"]["deployment/restore/recovery_and.py"]
    raw = json.dumps(manifest).encode()
    (bundle / "manifest.json").write_bytes(raw)
    with pytest.raises(install.InstallError, match="fixed_source_closure"):
        install.closure(bundle, hashlib.sha256(raw).hexdigest())


def test_source_symlink_and_mismatched_sql_pin_reject(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    checksum = install.prepare(CODE, bundle)
    file = bundle / "deployment/restore/recovery_and.py"
    data = file.read_bytes()
    file.unlink()
    outside = tmp_path / "outside.py"
    outside.write_bytes(data)
    file.symlink_to(outside)
    with pytest.raises(OSError, match="Too many levels of symbolic links"):
        install.closure(bundle, checksum)
    content = {name: install.read_file(CODE, name) for name in install.FILES}
    content["deployment/restore/recovery_catalog.sql"] += b"\n"
    with pytest.raises(install.InstallError, match="matched_capture_sql_pins_required"):
        install.validate_sql_pins(content)


def test_prepare_never_overwrites_existing_bundle(tmp_path: Path) -> None:
    destination = tmp_path / "existing"
    destination.mkdir()
    sentinel = destination / "keep"
    sentinel.write_text("retained")
    with pytest.raises(FileExistsError):
        install.prepare(CODE, destination)
    assert sentinel.read_text() == "retained"


def test_actual_install_requires_root_before_any_host_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    with pytest.raises(install.InstallError, match="root_install_required"):
        install.install(Path("/not-opened"), "a" * 64, Path("/usr/bin/python3"), with_ca=False)


@pytest.mark.parametrize("runtime", ["/usr/bin/python3;touch-x", "/usr/bin/../bin/python3"])
def test_unit_executable_cannot_inject_systemd_arguments(tmp_path: Path, runtime: str) -> None:
    bundle = tmp_path / "bundle"
    checksum = install.prepare(CODE, bundle)
    contents = install.closure(bundle, checksum)
    with pytest.raises(install.InstallError, match="installed_executable_path"):
        install.render_units(
            contents, Path("/usr/local/lib/peerly-backup/releases") / checksum, Path(runtime), False
        )


def test_source_walk_cannot_follow_directory_symlink_or_traversal(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (real / "source.py").write_text("safe")
    (tmp_path / "link").symlink_to(real, target_is_directory=True)
    with pytest.raises(NotADirectoryError):
        install.read_file(tmp_path, "link/source.py")
    with pytest.raises(install.InstallError, match="source_path"):
        install.read_file(tmp_path, "../source.py")


def test_duplicate_manifest_keys_reject_even_with_matching_raw_pin(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    install.prepare(CODE, bundle)
    raw = b'{"format":1,"format":1,"files":{}}'
    (bundle / "manifest.json").write_bytes(raw)
    with pytest.raises(install.InstallError, match="manifest_duplicate"):
        install.closure(bundle, hashlib.sha256(raw).hexdigest())
