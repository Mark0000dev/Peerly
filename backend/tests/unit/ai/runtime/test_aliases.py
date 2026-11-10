"""Alias probe protocol failures never become all-tool/real-credential acceptance."""

from pathlib import Path

import pytest

from studymate.infrastructure.ai.runtime import aliases
from studymate.infrastructure.ai.runtime.aliases import prove_cli_auth_aliases
from studymate.infrastructure.ai.runtime.preflight import CliInspectionError, InspectionOutput
from tests.unit.ai.runtime.test_preflight import system_pin


@pytest.mark.parametrize(
    "case",
    [
        (
            0,
            0,
            b'{"read_aliases_denied":true,"cache_writes_denied":true,"marker_fd_denied":true}',
            None,
        ),
        (1, 0, b"", "transport_positive_control"),
        (0, 11, b"", "cli_auth_alias_denial"),
        (0, 0, b"not json", "cli_auth_alias_output"),
        (0, 0, b"{}", "cli_auth_alias_output"),
    ],
)
async def test_alias_result_contract_and_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: tuple[int, int, bytes, str | None]
) -> None:
    positive_exit, exit_code, output, error = case
    private = tmp_path / "private-cache"
    private.mkdir()
    marker = private / "auth.json"
    marker.write_bytes(b"SYNTHETIC_NOT_A_CREDENTIAL")
    calls = 0

    async def inspect(argv: tuple[str, ...], *, dedicated_home: Path) -> InspectionOutput:
        nonlocal calls
        calls += 1
        assert dedicated_home == tmp_path
        if calls == 1:
            return InspectionOutput(positive_exit, b"", b"")
        assert "sandbox" in argv
        assert "--permission-profile" in argv
        return InspectionOutput(exit_code, output, b"")

    monkeypatch.setattr(aliases, "inspect_command", inspect)
    pin = await system_pin()
    if error is not None:
        with pytest.raises(CliInspectionError, match=error):
            await prove_cli_auth_aliases(pin, tmp_path, marker)
    else:
        result = await prove_cli_auth_aliases(pin, tmp_path, marker)
        assert result.transport_read_write
        assert result.marker_fd_denied
        assert not result.all_model_tools_proven
        assert not result.real_credential_refresh_proven
    assert not (tmp_path / "synthetic-public-link").is_symlink()


async def test_alias_marker_requires_private_directory(tmp_path: Path) -> None:
    pin = await system_pin()
    with pytest.raises(ValueError, match="private child"):
        await prove_cli_auth_aliases(pin, tmp_path, tmp_path / "marker")
