"""Permission probe result contracts; real native helper evidence is separate."""

from pathlib import Path

import pytest

from studymate.infrastructure.ai.runtime import permissions
from studymate.infrastructure.ai.runtime.permissions import prove_cli_read_denial
from studymate.infrastructure.ai.runtime.preflight import CliInspectionError, InspectionOutput
from tests.unit.ai.runtime.test_preflight import system_pin


@pytest.mark.parametrize(
    "case",
    [
        (0, 0, b'{"helper_auth_path_denied":true}', None),
        (1, 0, b"", "synthetic_marker_positive_control"),
        (0, 11, b"", "cli_helper_denial_failed"),
        (0, 0, b"not json", "cli_helper_denial_output"),
        (0, 0, b'{"helper_auth_path_denied":false}', "cli_helper_denial_output"),
    ],
)
async def test_helper_evidence_fails_closed_without_claiming_all_tool_routing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: tuple[int, int, bytes, str | None],
) -> None:
    positive_exit, exit_code, output, error = case
    calls = 0

    async def inspect(argv: tuple[str, ...], *, dedicated_home: Path) -> InspectionOutput:
        nonlocal calls
        calls += 1
        assert dedicated_home == tmp_path
        if calls == 1:
            return InspectionOutput(positive_exit, b"", b"")
        assert "sandbox" in argv
        assert "--permission-profile" in argv
        assert "permissions.peerly.network.enabled=false" in argv
        return InspectionOutput(exit_code, output, b"")

    monkeypatch.setattr(permissions, "inspect_command", inspect)
    pin = await system_pin()
    marker = tmp_path / "private" / "synthetic-marker"
    if error is not None:
        with pytest.raises(CliInspectionError, match=error):
            await prove_cli_read_denial(pin, tmp_path, marker)
    else:
        result = await prove_cli_read_denial(pin, tmp_path, marker)
        assert result.helper_auth_path_denied
        assert not result.all_model_tools_proven


async def test_marker_cannot_mask_entire_job_or_be_outside_job(tmp_path: Path) -> None:
    pin = await system_pin()
    for path in (tmp_path / "marker", tmp_path.parent / "outside"):
        with pytest.raises(ValueError, match="private child"):
            await prove_cli_read_denial(pin, tmp_path, path)
