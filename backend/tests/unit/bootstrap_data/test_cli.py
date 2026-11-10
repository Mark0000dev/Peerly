"""Real offline CLI subprocesses; no database/settings or owner-authored files."""

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from tests.unit.bootstrap_data.data import encoded

ROOT = Path(__file__).resolve().parents[3]
PROBE = """
import sys
from studymate.bootstrap_data_cli import main
result = main(sys.argv[1:])
if sys.argv[1] in ('schema', 'validate'):
    assert 'studymate.config' not in sys.modules
    assert 'sqlalchemy' not in sys.modules
raise SystemExit(result)
"""


async def invoke(
    tmp_path: Path, *arguments: str, database_url: str | None = None
) -> tuple[int, str, str]:
    environment = {
        "PATH": os.defpath,
        "PYTHONPATH": str(ROOT / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if database_url is not None:
        environment["DATABASE_URL"] = database_url
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        PROBE,
        *arguments,
        cwd=tmp_path,
        env=environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
    finally:
        if process.returncode is None:
            process.kill()
            await process.communicate()
    assert process.returncode is not None
    return process.returncode, stdout.decode(), stderr.decode()


async def test_schema_is_real_json_and_never_imports_settings_or_database(tmp_path: Path) -> None:
    code, output, errors = await invoke(tmp_path, "schema", database_url="PRIVATE_BAD_DSN")
    assert code == 0
    assert not errors
    assert json.loads(output)["additionalProperties"] is False
    assert "PRIVATE_BAD_DSN" not in output


@pytest.mark.parametrize("database_url", [None, "PRIVATE_BAD_DSN"])
async def test_validate_succeeds_without_database_configuration_and_never_echoes_content(
    tmp_path: Path, database_url: str | None
) -> None:
    path = tmp_path / "synthetic-authored.json"
    path.write_bytes(encoded())
    code, output, errors = await invoke(tmp_path, "validate", str(path), database_url=database_url)
    assert code == 0
    assert not errors
    assert json.loads(output) == {
        "status": "valid",
        "schema_version": 1,
        "policy_count": 2,
        "subject_count": 1,
        "alias_count": 1,
    }
    assert "PRIVATE" not in output
    assert "Synthetic Subject" not in output


async def test_apply_requires_database_env_but_validates_bad_file_before_configuration(
    tmp_path: Path,
) -> None:
    path = tmp_path / "synthetic.json"
    path.write_bytes(encoded())
    code, output, errors = await invoke(tmp_path, "apply", str(path))
    assert code != 0
    assert not errors
    assert json.loads(output)["code"] == "database_configuration"
    path.write_bytes(b'{"PRIVATE_INPUT":true}')
    code, output, errors = await invoke(tmp_path, "apply", str(path))
    assert code != 0
    assert not errors
    assert json.loads(output)["code"] == "invalid_input"
    assert "PRIVATE_INPUT" not in output


async def test_database_url_argument_is_not_supported_or_echoed(tmp_path: Path) -> None:
    code, output, errors = await invoke(
        tmp_path,
        "apply",
        "synthetic.json",
        "--database-url",
        "postgresql+asyncpg://private:PRIVATE_PASSWORD@host/db",
    )
    assert code != 0
    assert not errors
    assert json.loads(output)["code"] == "invalid_arguments"
    assert "PRIVATE_PASSWORD" not in output
