"""Private configuration hold/exec boundaries; synthetic temporary files only."""

import os
import signal
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from deployment.backend import provision_bootstrap as bootstrap


def write(path: Path, data: object) -> None:
    import json

    path.write_text(json.dumps(data))
    path.chmod(0o600)


def test_valid_configuration_and_absent_file(tmp_path: Path) -> None:
    path = tmp_path / "worker-env.json"
    with pytest.raises(FileNotFoundError):
        bootstrap.load_configuration(path)
    write(path, {"DATABASE_URL": "synthetic", "RUNTIME__MODEL": "synthetic-model"})
    values = bootstrap.load_configuration(path)
    assert values["RUNTIME__MODEL"] == "synthetic-model"
    assert "RUNTIME__MAX_PROCESSES" not in values


def test_symlink_file_and_parent_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "worker-env.json"
    write(path, {"DATABASE_URL": "synthetic"})
    alias = tmp_path / "alias"
    alias.symlink_to(path)
    with pytest.raises(OSError, match=r"Not a directory|Too many levels"):
        bootstrap.load_configuration(alias)
    directory = tmp_path / "parent-alias"
    directory.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(OSError, match=r"Not a directory|Too many levels"):
        bootstrap.load_configuration(directory / path.name)


def test_fifo_directory_and_hardlink_rejected(tmp_path: Path) -> None:
    path = tmp_path / "worker-env.json"
    os.mkfifo(path, 0o600)
    with pytest.raises(bootstrap.InvalidConfigurationError):
        bootstrap.load_configuration(path)
    path.unlink()
    path.mkdir()
    with pytest.raises(bootstrap.InvalidConfigurationError):
        bootstrap.load_configuration(path)
    path.rmdir()
    write(path, {"DATABASE_URL": "synthetic"})
    os.link(path, tmp_path / "hardlink")
    with pytest.raises(bootstrap.InvalidConfigurationError):
        bootstrap.load_configuration(path)


def test_writable_metadata_and_foreign_owner_rejected(tmp_path: Path) -> None:
    path = tmp_path / "worker-env.json"
    write(path, {"DATABASE_URL": "synthetic"})
    for mode in (0o620, 0o602):
        path.chmod(mode)
        with pytest.raises(bootstrap.InvalidConfigurationError):
            bootstrap.load_configuration(path)
    path.chmod(0o600)
    metadata = path.stat()
    foreign = os.stat_result(
        (
            metadata.st_mode,
            metadata.st_ino,
            metadata.st_dev,
            metadata.st_nlink,
            987654,
            metadata.st_gid,
            metadata.st_size,
            metadata.st_atime,
            metadata.st_mtime,
            metadata.st_ctime,
        )
    )
    with (
        patch.object(os, "fstat", return_value=foreign),
        pytest.raises(bootstrap.InvalidConfigurationError),
    ):
        bootstrap.load_configuration(path)


def test_size_types_unknown_keys_and_injection_rejected(tmp_path: Path) -> None:
    path = tmp_path / "worker-env.json"
    cases: tuple[object, ...] = (
        [],
        {},
        {"LD_PRELOAD": "bad"},
        {"CODEX_HOME": "/bad"},
        {"RUNTIME__MODEL": 1},
        {"DATABASE_URL": ""},
        {"DATABASE_URL": "bad\x00"},
        {"DATABASE_URL": "bad\n"},
        {"DATABASE_URL": "x" * 8193},
        {"RUNTIME__MAX_PROCESS": "40"},
    )
    for data in cases:
        write(path, data)
        with pytest.raises(bootstrap.InvalidConfigurationError):
            bootstrap.load_configuration(path)
    path.write_bytes(b"x" * (bootstrap.MAX_BYTES + 1))
    with pytest.raises(bootstrap.InvalidConfigurationError):
        bootstrap.load_configuration(path)


def test_duplicates_encoding_and_nonabsolute_paths_rejected(tmp_path: Path) -> None:
    path = tmp_path / "worker-env.json"
    for data in (
        b'{"DATABASE_URL":"first","DATABASE_URL":"second"}',
        b"\xff",
        b"{",
    ):
        path.write_bytes(data)
        path.chmod(0o600)
        with pytest.raises(bootstrap.InvalidConfigurationError):
            bootstrap.load_configuration(path)
    for invalid in (Path("relative"), tmp_path / ".." / "bad"):
        with pytest.raises(bootstrap.InvalidConfigurationError):
            bootstrap.load_configuration(invalid)


@pytest.mark.parametrize("limit", [None, "32", "40"])
def test_exec_replaces_environment_and_forwards_only_explicit_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    limit: str | None,
) -> None:
    path = tmp_path / "worker-env.json"
    config = {"DATABASE_URL": "synthetic"}
    if limit is not None:
        config["RUNTIME__MAX_PROCESSES"] = limit
    write(path, config)
    captured: list[tuple[str, tuple[str, ...], dict[str, str]]] = []

    def execute(executable: str, arguments: tuple[str, ...], environment: dict[str, str]) -> None:
        captured.append((executable, arguments, environment))

    monkeypatch.setenv("OPENAI_API_KEY", "must-not-propagate")
    monkeypatch.setenv("LD_PRELOAD", "must-not-propagate")
    monkeypatch.setattr(os, "execve", execute)
    bootstrap.activate(bootstrap.load_configuration(path))
    executable, arguments, environment = captured[0]
    assert arguments == (executable, "-m", "studymate.ai_worker")
    assert environment == bootstrap.BASE_ENVIRONMENT | config
    assert "OPENAI_API_KEY" not in environment
    assert "LD_PRELOAD" not in environment
    assert ("RUNTIME__MAX_PROCESSES" in environment) == (limit is not None)


def test_timeout_and_rejection_never_exec_or_echo_values(
    capsys: pytest.CaptureFixture[str],
) -> None:
    for clock, error in (
        ([0, 2], FileNotFoundError()),
        ([0, 0], bootstrap.InvalidConfigurationError("synthetic-private-value")),
    ):
        with (
            patch.object(sys, "argv", ["bootstrap", "--wait-seconds", "1"]),
            patch.object(signal, "signal"),
            patch.object(time, "monotonic", side_effect=clock),
            patch.object(bootstrap, "load_configuration", side_effect=error),
            patch.object(bootstrap, "activate") as activate,
        ):
            assert bootstrap.main() == 1
            activate.assert_not_called()
        output = capsys.readouterr()
        assert "synthetic-private-value" not in output.out + output.err
