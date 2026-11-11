"""Probe result/error contract tests; actual namespace evidence is recorded separately."""

from pathlib import Path

import pytest

from studymate.infrastructure.ai.runtime import probe
from studymate.infrastructure.ai.runtime.namespace import OfflineNamespace
from studymate.infrastructure.ai.runtime.preflight import CliInspectionError, InspectionOutput
from studymate.infrastructure.ai.runtime.probe import prove_offline_namespace


@pytest.mark.parametrize(
    ("exit_code", "output", "error"),
    [
        (
            0,
            b'{"marker_denied":true,"environment_denied":true,"descriptor_denied":true,"private_namespaces":true,"host_network_denied":true}',
            None,
        ),
        (11, b"", "namespace_denial_failed"),
        (0, b"not json", "namespace_probe_output"),
        (0, b'{"marker_denied":false}', "namespace_probe_output"),
    ],
)
async def test_namespace_result_contract_never_claims_cli_tools_or_cgroup_acceptance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exit_code: int,
    output: bytes,
    error: str | None,
) -> None:
    job = tmp_path / "job"
    job.mkdir()
    marker = tmp_path / "synthetic-private-marker"
    marker.write_text("SYNTHETIC_ONLY")

    async def inspect(
        argv: tuple[str, ...], *, synthetic_environment_marker: bool
    ) -> InspectionOutput:
        assert synthetic_environment_marker
        assert "--unshare-all" in argv
        assert "--clearenv" in argv
        return InspectionOutput(exit_code, output, b"")

    monkeypatch.setattr(probe, "inspect_command", inspect)
    if error is not None:
        with pytest.raises(CliInspectionError, match=error):
            await prove_offline_namespace(OfflineNamespace(), job, marker)
    else:
        result = await prove_offline_namespace(OfflineNamespace(), job, marker)
        assert result.marker_denied
        assert result.private_namespaces
        assert not result.cli_tool_routing_proven
        assert not result.aggregate_cgroup_proven


async def test_marker_must_not_be_inside_job_mount(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="outside"):
        await prove_offline_namespace(OfflineNamespace(), tmp_path, tmp_path / "auth.json")
