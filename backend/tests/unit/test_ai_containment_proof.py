"""Credential-free runner contracts; no native CLI, namespace or remote execution."""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Literal
from unittest.mock import AsyncMock, patch

import pytest
from deployment.backend import prove_ai_containment as proof

from studymate.infrastructure.ai.process import TerminationUncertainError
from studymate.infrastructure.ai.runtime.acceptance import policy_digest
from studymate.infrastructure.ai.runtime.policy import INSPECTED_VERSION, InspectionPolicy


def evidence(phase: Literal["outer", "nested"], maximum: int, *, otlp: bool = False) -> bytes:
    positive = phase == "outer"
    return (
        proof.ChildEvidence(
            phase=phase,
            private_paths_denied=True,
            marker_fd_denied=True,
            proc_escape_denied=True,
            environment_denied=True,
            private_namespaces=True,
            usr_write_denied=True,
            auth_readable=positive,
            auth_writable=positive,
            job_writable=positive,
            transport_control="reachable" if positive else "denied",
            otlp_control=("reachable" if positive else "denied") if otlp else "not_requested",
            nproc=(maximum, maximum),
            address_space=(proof.MEMORY, proof.MEMORY),
            scratch_bytes=32 * 1024 * 1024 if positive else None,
        )
        .model_dump_json()
        .encode()
    )


class SyntheticRunner(proof.Runner):
    """Only synthetic child results; inherited probes still compose production argv."""

    calls: list[tuple[str, ...]]
    nested_override: bytes | None = None
    startup: bytes = b'{"synthetic_config":true}'
    stop_uncertain: bool = False

    def controller(self) -> dict[str, str]:
        return dict.fromkeys(proof.NAMESPACES, "synthetic-controller-namespace")

    async def verify_identity(self) -> None:
        return None

    async def connect_control(self) -> bool | None:
        return True if self.configuration.otlp_ip else None

    async def child(self, invocation: tuple[str, ...], job: Path, auth: Path) -> bytes:
        self.calls.append(invocation)
        assert await asyncio.to_thread(job.is_dir)
        assert await asyncio.to_thread(auth.is_dir)
        assert (auth / "synthetic-marker").read_bytes() == proof.SYNTHETIC
        assert not (auth / "auth.json").exists()
        if self.stop_uncertain:
            self.stopped = False
            raise proof.ProofError("stop_uncertain")
        if invocation[1] == "--version":
            return INSPECTED_VERSION.encode()
        if invocation[1] == "app-server":
            return self.startup
        phase: Literal["outer", "nested"] = "nested" if invocation[1] == "sandbox" else "outer"
        if phase == "nested" and self.nested_override is not None:
            return self.nested_override
        return evidence(
            phase, self.configuration.max_processes, otlp=bool(self.configuration.otlp_ip)
        )


def runner(tmp_path: Path, maximum: int = 32, otlp_ip: str | None = None) -> SyntheticRunner:
    instance = SyntheticRunner(proof.Configuration(maximum, otlp_ip, tmp_path))
    instance.calls = []
    return instance


@pytest.mark.parametrize("maximum", [31, 41, 0, -1, True])
def test_rejects_unbounded_or_invalid_process_limit(maximum: int) -> None:
    with pytest.raises(ValueError, match="process bound"):
        proof.Configuration(maximum)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "localhost",
        "8.8.8.8",
        "http://10.0.0.1",
        "10.0.0.1:4318",
        "169.254.1.1",
        "::1",
        "10.00.0.1",
    ],
)
def test_otlp_is_canonical_numeric_rfc1918_only(address: str) -> None:
    with pytest.raises(proof.ProofError, match="configuration"):
        proof.Configuration(32, address)


def test_reuses_production_policy_and_explicit_finite_child_limits(tmp_path: Path) -> None:
    baseline = runner(tmp_path)
    expanded = runner(tmp_path, 40)
    for instance in (baseline, expanded):
        maximum = instance.configuration.max_processes
        command = instance.sandbox.command((str(proof.CLI), "--version"), tmp_path / "job")
        assert f"--nproc={maximum}" in command
        assert "--as=1073741824" in command
        assert "--cap-drop" in command
        assert "--share-net" in command
        assert str(instance.sandbox.bubblewrap) in command
    assert (
        policy_digest(baseline.cli)
        == "ee0382dae2d63e2bb64b1ee778cc15388aa8d58e21670cc8eb2f099a892a1bf8"
    )
    assert (
        policy_digest(expanded.cli, max_processes=40)
        == "c619f1d2eec4daf5afa6182910519471c56ce53fc3c06073482506f7ef4ba8a7"
    )
    compile(proof.CHILD, "<fixed-stdlib-probe>", "exec")


@pytest.mark.parametrize(("maximum", "otlp_ip"), [(32, None), (40, "172.20.0.2")])
async def test_complete_closed_diagnostic_not_receipt_or_provider_grant(
    tmp_path: Path,
    maximum: int,
    otlp_ip: str | None,
) -> None:
    instance = runner(tmp_path, maximum, otlp_ip)
    with patch.object(proof, "native_python", return_value=Path("/usr/local/bin/python3")):
        result = await instance.run()
    assert result.result == "PASS"
    assert not result.cleanup_pending
    assert result.physical_groups_stopped
    assert result.controller_otlp_positive == (True if otlp_ip else None)
    assert not result.receipt_issued
    assert not result.provider_called
    assert not result.model_tasks_proven
    assert not result.all_model_tools_proven
    assert not result.whole_container_stopped
    assert not await asyncio.to_thread(lambda: list(tmp_path.iterdir()))
    assert proof.ENV_MARKER not in os.environ
    nested = instance.calls[2]
    assert nested[:4] == (str(proof.CLI), "sandbox", "--permission-profile", "peerly")
    job = Path(nested[5])
    assert InspectionPolicy(job, job / "auth", maximum).overrides(instance.cli) == nested[6:-5]
    assert nested[-5:-1] == ("--", "/usr/local/bin/python3", "-c", proof.CHILD)


@pytest.mark.parametrize(
    "change",
    [
        {"phase": "outer"},
        {"auth_readable": True},
        {"auth_writable": True},
        {"job_writable": True},
        {"transport_control": "reachable"},
        {"otlp_control": "reachable"},
        {"nproc": [32, 32]},
        {"address_space": [-1, -1]},
        {"scratch_bytes": 1024},
        {"marker_fd_denied": False},
        {"unexpected": "never-echo-this"},
    ],
)
async def test_contradictory_or_open_child_output_rejected_and_owned_cleanup(
    tmp_path: Path,
    change: dict[str, object],
) -> None:
    instance = runner(tmp_path, 40, "10.0.0.2")
    payload = proof.ChildEvidence.model_validate_json(evidence("nested", 40, otlp=True))
    instance.nested_override = (
        payload.model_dump_json()[:-1] + "," + json.dumps(change)[1:]
    ).encode()
    with patch.object(proof, "native_python", return_value=Path("/usr/local/bin/python3")):
        result = await instance.run()
    assert result.failure == "output_invalid"
    assert result.result == "FAIL"
    assert not result.cleanup_pending
    assert "never-echo-this" not in result.model_dump_json()


async def test_malformed_and_empty_startup_output_fail_closed(tmp_path: Path) -> None:
    instance = runner(tmp_path)
    instance.nested_override = b"RAW_PRIVATE_LOOKING_NEVER_ECHO"
    with patch.object(proof, "native_python", return_value=Path("/usr/local/bin/python3")):
        malformed = await instance.run()
        instance.nested_override = None
        instance.startup = b""
        empty = await instance.run()
    assert malformed.failure == empty.failure == "output_invalid"
    assert "RAW_PRIVATE" not in malformed.model_dump_json()


async def test_uncertain_physical_stop_retains_only_owned_context(tmp_path: Path) -> None:
    instance = runner(tmp_path)
    instance.stop_uncertain = True
    result = await instance.run()
    assert result.failure == "stop_uncertain"
    assert result.cleanup_pending
    assert not result.physical_groups_stopped
    assert instance.context is not None
    assert await asyncio.to_thread(instance.context.is_dir)
    assert instance.job_directory is not None
    assert (instance.job_directory / "auth/synthetic-marker").read_bytes() == proof.SYNTHETIC
    assert (instance.context / "outside-marker").read_bytes() == proof.SYNTHETIC


async def test_context_collision_never_deletes_unowned_directory(tmp_path: Path) -> None:
    instance = runner(tmp_path)
    unrelated = tmp_path / ("peerly-containment-" + instance.proof_id)
    unrelated.mkdir()
    marker = unrelated / "unowned-marker"
    marker.write_text("synthetic-unowned")
    result = await instance.run()
    assert result.result == "FAIL"
    assert instance.context is None
    assert marker.read_text() == "synthetic-unowned"


async def test_production_stop_uncertainty_is_not_suppressed(tmp_path: Path) -> None:
    instance = proof.Runner(proof.Configuration(32, workspaces=tmp_path))
    instance.stopped = False
    process = AsyncMock(spec=asyncio.subprocess.Process)
    with (
        patch.object(proof, "production_stop", side_effect=TerminationUncertainError),
        pytest.raises(proof.ProofError, match="stop_uncertain"),
    ):
        await instance.stop(process)
    assert not instance.stopped


async def test_fixed_stop_reaps_owned_real_synthetic_child(tmp_path: Path) -> None:
    instance = proof.Runner(proof.Configuration(32, workspaces=tmp_path))
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        "-c",
        "import time; time.sleep(30)",
        start_new_session=True,
        close_fds=True,
    )
    instance.stopped = False
    try:
        await instance.stop(child)
    finally:
        if child.returncode is None:
            child.kill()
            await child.wait()
    assert instance.stopped
    assert child.returncode is not None
    with pytest.raises(ProcessLookupError):
        os.killpg(child.pid, 0)


async def test_bounded_drain_does_not_report_or_retain_oversized_output(tmp_path: Path) -> None:
    instance = proof.Runner(proof.Configuration(32, workspaces=tmp_path))
    stream = asyncio.StreamReader()
    stream.feed_data(b"x" * (proof.OUTPUT_MAX + 1))
    stream.feed_eof()
    with pytest.raises(proof.ProofError, match="output_bound"):
        await instance.drain(stream)


async def test_closed_cli_error_never_echoes_untrusted_argument(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with patch.object(sys, "argv", ["prove_ai_containment.py", "--untrusted=PRIVATE"]):
        status = await proof.main_async()
    captured = capsys.readouterr()
    assert status == 1
    assert "PRIVATE" not in captured.out + captured.err
    assert "configuration" in captured.out


async def test_actual_cgroup_must_equal_selected_child_bound(tmp_path: Path) -> None:
    instance = proof.Runner(proof.Configuration(40, workspaces=tmp_path))

    def kernel_text(path: Path) -> str:
        values = {
            "/proc/self/status": "NoNewPrivs:\t1\nCapEff:\t0000000000000000\n",
            "/sys/fs/cgroup/pids.max": "32",
            "/sys/fs/cgroup/memory.max": str(proof.MEMORY),
            "/sys/fs/cgroup/cpu.max": proof.CPU_MAX,
        }
        return values[str(path)]

    volume = os.statvfs_result((4096, 4096, 1, 1, 1, 1, 1, 1, os.ST_RDONLY, 255))
    with (
        patch.object(os, "geteuid", return_value=proof.UID),
        patch.object(os, "getegid", return_value=proof.UID),
        patch.object(os, "statvfs", return_value=volume),
        patch.object(Path, "read_text", autospec=True, side_effect=kernel_text),
        pytest.raises(proof.ProofError, match="controller_limits"),
    ):
        instance.controller()
    assert instance.context is None


async def test_child_deadline_still_uses_production_stop_and_safe_spawn_environment(
    tmp_path: Path,
) -> None:
    instance = proof.Runner(proof.Configuration(32, workspaces=tmp_path))
    job, auth, _outside = instance.prepare()
    invocation = (str(proof.CLI), "--version")
    real_create = asyncio.create_subprocess_exec
    children: list[asyncio.subprocess.Process] = []

    async def spawn(*args: str, **kwargs: object) -> asyncio.subprocess.Process:
        assert args == instance.sandbox.command(invocation, job)
        assert kwargs["close_fds"] is True
        assert kwargs["start_new_session"] is True
        assert kwargs["cwd"] == job
        assert kwargs["limit"] == proof.DRAIN_CHUNK
        assert kwargs["env"] == {
            "PATH": "/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "HOME": str(job),
            "CODEX_HOME": str(auth),
            "TMPDIR": "/scratch",
        }
        child = await real_create(
            sys.executable,
            "-I",
            "-c",
            "import time; time.sleep(30)",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
            close_fds=True,
        )
        children.append(child)
        return child

    with (
        patch.object(asyncio, "create_subprocess_exec", side_effect=spawn),
        patch.object(proof, "OPERATION_SECONDS", 0.02),
        pytest.raises(TimeoutError),
    ):
        await instance.child(invocation, job, auth)
    assert instance.stopped
    assert len(children) == 1
    assert children[0].returncode is not None
    with pytest.raises(ProcessLookupError):
        os.killpg(children[0].pid, 0)


async def test_cancellation_while_spawn_handle_pending_still_confirms_stop(tmp_path: Path) -> None:
    instance = proof.Runner(proof.Configuration(32, workspaces=tmp_path))
    job, auth, _outside = instance.prepare()
    real_create = asyncio.create_subprocess_exec
    ready = asyncio.Event()
    deliver = asyncio.Event()
    children: list[asyncio.subprocess.Process] = []

    async def spawn(*_args: str, **_kwargs: object) -> asyncio.subprocess.Process:
        child = await real_create(
            sys.executable,
            "-I",
            "-c",
            "import time; time.sleep(30)",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
            close_fds=True,
        )
        children.append(child)
        ready.set()
        await deliver.wait()
        return child

    with patch.object(asyncio, "create_subprocess_exec", side_effect=spawn):
        task = asyncio.create_task(instance.child((str(proof.CLI), "--version"), job, auth))
        try:
            async with asyncio.timeout(3):
                await ready.wait()
                task.cancel()
                deliver.set()
                with pytest.raises(asyncio.CancelledError):
                    await task
        finally:
            deliver.set()
            for child in children:
                if child.returncode is None:
                    child.kill()
                    await child.wait()
    assert instance.stopped
    assert len(children) == 1
    with pytest.raises(ProcessLookupError):
        os.killpg(children[0].pid, 0)


async def test_otlp_controller_failure_is_finite_and_never_runs_probe(tmp_path: Path) -> None:
    instance = proof.Runner(proof.Configuration(40, "10.20.0.2", tmp_path))
    with (
        patch.object(asyncio, "open_connection", side_effect=OSError("PRIVATE_MUST_NOT_ESCAPE")),
        pytest.raises(proof.ProofError, match=r"^controller_otlp$"),
    ):
        await instance.connect_control()
    assert instance.context is None


def test_probe_job_matches_actual_production_depth_and_control_marker_is_unmounted(
    tmp_path: Path,
) -> None:
    instance = proof.Runner(proof.Configuration(40, workspaces=tmp_path))
    job, auth, outside = instance.prepare()
    assert job.parent == tmp_path
    assert job.name.startswith("peerly-ai-")
    assert auth == job / "auth"
    assert instance.job_directory == job
    assert instance.context is not None
    assert outside.parent == instance.context
    assert instance.context.parent == tmp_path
    assert instance.context != job
    assert not outside.is_relative_to(job)
    command = instance.sandbox.command((str(proof.CLI), "--version"), job)
    bind = command.index("--bind")
    assert command[bind + 1 : bind + 3] == (str(job), str(job))
    assert str(instance.context) not in command
    assert outside.read_bytes() == proof.SYNTHETIC


async def test_job_collision_cleans_only_new_control_directory(tmp_path: Path) -> None:
    instance = runner(tmp_path)
    unrelated = tmp_path / ("peerly-ai-" + instance.proof_id)
    unrelated.mkdir()
    marker = unrelated / "unowned-marker"
    marker.write_text("synthetic-unowned")
    result = await instance.run()
    assert result.failure == "configuration"
    assert instance.job_directory is None
    assert instance.context is not None
    assert not await asyncio.to_thread(instance.context.exists)
    assert marker.read_text() == "synthetic-unowned"


async def test_partial_auth_directory_failure_cleans_both_owned_siblings(tmp_path: Path) -> None:
    instance = runner(tmp_path)
    original_mkdir = Path.mkdir

    def mkdir(path: Path, mode: int = 0o777, parents: bool = False, exist_ok: bool = False) -> None:
        if path.name == "auth":
            raise OSError("Synthetic auth directory creation failure")
        original_mkdir(path, mode=mode, parents=parents, exist_ok=exist_ok)

    with patch.object(Path, "mkdir", autospec=True, side_effect=mkdir):
        result = await instance.run()
    assert result.failure == "configuration"
    assert not result.cleanup_pending
    assert result.physical_groups_stopped
    assert not await asyncio.to_thread(lambda: list(tmp_path.iterdir()))
