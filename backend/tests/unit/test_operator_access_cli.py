"""Strict owner-only input and safe failure boundary; no authenticated public route."""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from deployment.backend import operator_access as cli


def manifest() -> dict[str, object]:
    return {
        "database": "peerly_staging",
        "performed_by": str(uuid4()),
        "account_id": str(uuid4()),
        "expected_version": 0,
        "active": True,
    }


def test_explicit_assignment_preserves_actual_ids_and_cas() -> None:
    value = manifest()
    command = cli.parse_manifest(json.dumps(value).encode())
    assert str(command.account_id) == value["account_id"]
    assert str(command.performed_by) == value["performed_by"]
    assert command.expected_version == 0
    assert command.active is True
    assert command.database == "peerly_staging"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("active", 1),
        ("active", "true"),
        ("expected_version", True),
        ("expected_version", -1),
        ("expected_version", cli.MAX_VERSION),
        ("database", ""),
        ("database", "a" * (cli.MAX_DATABASE_LENGTH + 1)),
        ("account_id", "person@example.com"),
        ("performed_by", None),
    ],
)
def test_rejects_coercion_and_invalid_scope(key: str, value: object) -> None:
    payload = manifest()
    payload[key] = value
    with pytest.raises(cli.OperatorAssignmentError, match="invalid_"):
        cli.parse_manifest(json.dumps(payload).encode())


def test_rejects_unknown_duplicate_and_oversized_input() -> None:
    payload = manifest()
    payload["email"] = "must-not-be-used@example.com"
    with pytest.raises(cli.OperatorAssignmentError, match="invalid_manifest"):
        cli.parse_manifest(json.dumps(payload).encode())
    with pytest.raises(cli.OperatorAssignmentError, match="duplicate_json_key"):
        cli.parse_manifest(b'{"active":true,"active":false}')
    with pytest.raises(cli.OperatorAssignmentError, match="input_too_large"):
        cli.parse_manifest(b" " * (cli.MAX_INPUT + 1))


def test_private_regular_file_and_symlink_guard(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    raw = json.dumps(manifest()).encode()
    path.write_bytes(raw)
    path.chmod(0o600)
    assert cli.read_input(str(path)) == raw
    path.chmod(0o644)
    with pytest.raises(cli.OperatorAssignmentError, match="unsafe_input_file"):
        cli.read_input(str(path))
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(OSError, match="Too many levels"):
        cli.read_input(str(link))
    with pytest.raises(cli.OperatorAssignmentError, match="unsafe_input_file"):
        cli.read_input(str(tmp_path))


async def test_config_rejects_wrong_driver_or_database_before_connect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command = cli.parse_manifest(json.dumps(manifest()).encode())
    for url in ["postgresql+asyncpg://u:p@localhost/default_db", "sqlite:///peerly_staging"]:
        monkeypatch.setenv("DATABASE_URL", url)
        with pytest.raises(cli.OperatorAssignmentError, match="wrong_database_configuration"):
            await cli.run(command, apply=True)


def test_invalid_arguments_never_echo_private_arguments(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["operator_access", "do-not-echo-private-value"])
    assert cli.main() == 1
    output = capsys.readouterr()
    assert json.loads(output.out) == {"status": "rejected", "code": "invalid_arguments"}
    assert output.err == ""
