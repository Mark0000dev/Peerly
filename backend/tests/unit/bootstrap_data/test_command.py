"""In-process safe exit-code mapping, supplementing actual offline subprocesses."""

import argparse
import json
from pathlib import Path

import pytest

from studymate import bootstrap_data_cli as cli
from studymate.application.bootstrap_data.apply import (
    BootstrapConflictCode,
    BootstrapConflictError,
    MissingPublishedPoliciesError,
)
from studymate.application.bootstrap_data.ports import (
    BootstrapDatabaseConfigurationError,
    BootstrapDatabaseOperationError,
)
from studymate.application.errors import StorageUnavailableError
from studymate.presentation.bootstrap_data.inputs import BootstrapInputCode, BootstrapInputError
from tests.unit.bootstrap_data.data import encoded


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (cli.BootstrapUsageError("PRIVATE"), 2, "invalid_arguments"),
        (BootstrapInputError(BootstrapInputCode.INPUT_FILE), 2, "input_file"),
        (BootstrapDatabaseConfigurationError("PRIVATE"), 2, "database_configuration"),
        (
            BootstrapConflictError(BootstrapConflictCode.MANIFEST_VERSION),
            3,
            "manifest_version_conflict",
        ),
        (MissingPublishedPoliciesError("PRIVATE"), 4, "current_policy_pair_required"),
        (BootstrapDatabaseOperationError("PRIVATE"), 5, "database_error"),
        (StorageUnavailableError("PRIVATE"), 5, "storage_unavailable"),
        (TimeoutError("PRIVATE"), 5, "database_error"),
    ],
)
def test_expected_failures_exit_nonzero_without_private_details(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
    status: int,
    code: str,
) -> None:
    async def failing_dispatch(_options: argparse.Namespace) -> int:
        raise error

    monkeypatch.setattr(cli, "dispatch", failing_dispatch)
    assert cli.main(["schema"]) == status
    output = capsys.readouterr()
    assert not output.err
    assert json.loads(output.out)["code"] == code
    assert "PRIVATE" not in output.out


async def test_actual_offline_dispatch_schema_validate_and_rejected_commands(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert await cli.dispatch(argparse.Namespace(command="schema")) == 0
    assert json.loads(capsys.readouterr().out)["additionalProperties"] is False
    path = tmp_path / "synthetic.json"
    path.write_bytes(encoded())
    assert await cli.dispatch(argparse.Namespace(command="validate", file=str(path))) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "valid"
    with pytest.raises(cli.BootstrapUsageError):
        await cli.dispatch(argparse.Namespace(command="validate"))
    with pytest.raises(cli.BootstrapUsageError):
        await cli.dispatch(argparse.Namespace(command="unknown", file=str(path)))


async def test_actual_apply_dispatch_missing_database_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    path = tmp_path / "synthetic.json"
    path.write_bytes(encoded())
    with pytest.raises(BootstrapDatabaseConfigurationError):
        await cli.dispatch(argparse.Namespace(command="apply", file=str(path)))
