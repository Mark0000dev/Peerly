import asyncio
import hashlib
import os
import sys
from pathlib import Path

import pytest

from studymate.infrastructure.ai.runtime import preflight
from studymate.infrastructure.ai.runtime.namespace import OfflineNamespace
from studymate.infrastructure.ai.runtime.preflight import (
    CliInspectionError,
    CliPreflight,
    InspectionOutput,
    PinnedCli,
    inspect_command,
)


@pytest.mark.parametrize("path", ["relative", "/home/forbidden", "/usr/../root/forbidden"])
def test_pin_rejects_non_native_runtime_locations(path: str) -> None:
    with pytest.raises(ValueError, match="Native"):
        PinnedCli(Path(path), "codex-cli 0.167.0", "a" * 64)


@pytest.mark.parametrize(
    ("version", "digest"), [("latest", "a" * 64), ("codex-cli 0.167.0", "bad")]
)
def test_pin_requires_exact_version_and_sha(version: str, digest: str) -> None:
    with pytest.raises(ValueError, match="exact version"):
        PinnedCli(Path("/usr/bin/unused"), version, digest)


async def system_pin() -> PinnedCli:
    executable = await asyncio.to_thread(Path(sys.executable).resolve)
    data = await asyncio.to_thread(executable.read_bytes)
    return PinnedCli(executable, "codex-cli 0.167.0", hashlib.sha256(data).hexdigest())


async def test_pin_hash_detects_wrong_binary_and_missing_executable() -> None:
    pin = await system_pin()
    await pin.verify()
    with pytest.raises(CliInspectionError, match="cli_identity"):
        await PinnedCli(pin.executable, pin.version, "0" * 64).verify()
    with pytest.raises(CliInspectionError, match="cli_identity"):
        await PinnedCli(Path("/usr/bin/peerly-nonexistent-cli"), pin.version, pin.sha256).verify()


async def test_inspector_bounds_output_and_preserves_nonzero_exit() -> None:
    output = await inspect_command(
        (sys.executable, "-c", "print('synthetic'); raise SystemExit(7)")
    )
    assert output.exit_code != 0
    assert output.stdout == b"synthetic\n"
    with pytest.raises(CliInspectionError, match="cli_output_bound"):
        await inspect_command((sys.executable, "-c", "print('x'*100000)"))


async def test_inspector_timeout_physically_reaps_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "synthetic-pid"
    monkeypatch.setattr(preflight, "INSPECTION_SECONDS", 0.1)
    program = (
        "import os,time,pathlib;"
        f"pathlib.Path({str(marker)!r}).write_text(str(os.getpid()));time.sleep(10)"
    )
    with pytest.raises(TimeoutError):
        await inspect_command((sys.executable, "-c", program))
    pid = int(marker.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


async def test_inspector_explicit_environment_does_not_inherit_parent_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "SYNTHETIC_PARENT_MARKER")
    program = (
        "import os;assert 'OPENAI_API_KEY' not in os.environ;"
        "assert 'PEERLY_SYNTHETIC_MARKER' in os.environ"
    )
    output = await inspect_command(
        (sys.executable, "-c", program), synthetic_environment_marker=True
    )
    assert output.exit_code == 0


async def test_version_and_config_probe_use_offline_namespace_and_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pin = await system_pin()
    output = InspectionOutput(0, pin.version.encode(), b"")

    async def inspect(argv: tuple[str, ...]) -> InspectionOutput:
        assert "--unshare-all" in argv
        assert "--clearenv" in argv
        assert "--share-net" not in argv
        return output

    monkeypatch.setattr(preflight, "inspect_command", inspect)
    probe = CliPreflight(pin, OfflineNamespace())
    await probe.version(tmp_path)
    output = InspectionOutput(1, b"", b"SYNTHETIC_PRIVATE_ERROR")
    with pytest.raises(CliInspectionError, match="cli_version"):
        await probe.version(tmp_path)
    assert await probe.configuration(tmp_path, ("-c", "unknown=true")) == output


@pytest.mark.parametrize("path", ["relative", "/", "/home/job", "/usr/job", "/usr/../root/job"])
def test_namespace_refuses_host_homes_or_ambient_runtime_roots(path: str) -> None:
    with pytest.raises(ValueError, match="directory"):
        OfflineNamespace().command(Path(path), ("/usr/bin/true",))


def test_namespace_refuses_relative_executables(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="executables"):
        OfflineNamespace().command(tmp_path, ("python",))


async def test_cancel_during_spawn_delivery_still_owns_and_reaps_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spawned = asyncio.Event()
    delivered = asyncio.Event()
    children: list[asyncio.subprocess.Process] = []
    original = asyncio.create_subprocess_exec

    async def delayed_spawn(*args: str, **kwargs: object) -> asyncio.subprocess.Process:
        # Preserve actual OS spawn, substituting only delivery timing.
        process = await original(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={"PATH": "/usr/bin:/bin"},
            start_new_session=True,
        )
        assert kwargs["close_fds"] is True
        children.append(process)
        spawned.set()
        await delivered.wait()
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", delayed_spawn)
    operation = asyncio.create_task(
        inspect_command((sys.executable, "-c", "import time;time.sleep(10)"))
    )
    await spawned.wait()
    operation.cancel()
    delivered.set()
    with pytest.raises(asyncio.CancelledError):
        await operation
    assert len(children) == 1
    assert children[0].returncode is not None
    with pytest.raises(ProcessLookupError):
        os.kill(children[0].pid, 0)


async def test_cancellation_waits_for_physical_inspection_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stopped = asyncio.Event()
    release = asyncio.Event()
    original = preflight.stop_inspection

    async def delayed_stop(process: asyncio.subprocess.Process) -> None:
        stopped.set()
        await release.wait()
        await original(process)

    monkeypatch.setattr(preflight, "stop_inspection", delayed_stop)
    operation = asyncio.create_task(inspect_command((sys.executable, "-c", "print('synthetic')")))
    await stopped.wait()
    operation.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await operation


async def test_native_digest_permission_failure_is_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pin = await system_pin()

    def denied(_self: Path, *args: object, **kwargs: object) -> None:
        del args, kwargs
        raise PermissionError("SYNTHETIC_PRIVATE_PATH")

    monkeypatch.setattr(Path, "open", denied)
    with pytest.raises(CliInspectionError, match="cli_identity") as error:
        await pin.verify()
    assert "PRIVATE" not in str(error.value)


async def test_direct_cli_inspection_requires_dedicated_non_home_context(tmp_path: Path) -> None:
    output = await inspect_command(
        (sys.executable, "-c", "import os;assert os.environ['CODEX_HOME'].endswith('/empty-auth')"),
        dedicated_home=tmp_path,
    )
    assert output.exit_code == 0
    with pytest.raises(ValueError, match="non-home"):
        await inspect_command(
            (sys.executable, "-c", "pass"), dedicated_home=Path("/home/forbidden")
        )


async def exited_inspection_child() -> asyncio.subprocess.Process:
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "pass",
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        env={"PATH": "/usr/bin:/bin"},
        start_new_session=True,
    )
    await child.wait()
    return child


async def test_inspection_waits_for_group_reap_after_leader_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    child = await exited_inspection_child()
    original = os.killpg
    probes = 0
    reap_visibility_polls = 3
    gone = asyncio.Event()

    def kernel(pid: int, sig: int) -> None:
        nonlocal probes
        assert pid == child.pid
        if sig != 0:
            original(pid, sig)
            return
        probes += 1
        if probes <= reap_visibility_polls:
            return
        gone.set()
        raise ProcessLookupError

    monkeypatch.setattr(os, "killpg", kernel)
    await preflight.stop_inspection(child)
    assert gone.is_set()
    assert child.returncode == 0


async def test_inspection_group_deadline_stays_typed_uncertain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from studymate.application.ai.ports import AiExecutorStateUncertainError
    from studymate.infrastructure.ai import process

    child = await exited_inspection_child()
    original = os.killpg

    def kernel(pid: int, sig: int) -> None:
        assert pid == child.pid
        if sig != 0:
            original(pid, sig)
        # The synthetic kernel never confirms disappearance of the group.

    monkeypatch.setattr(os, "killpg", kernel)
    monkeypatch.setattr(process, "STOP_CONFIRM_SECONDS", 0.03)
    with pytest.raises(AiExecutorStateUncertainError, match="physical stop"):
        await preflight.stop_inspection(child)


async def test_inspection_leader_wait_deadline_is_not_ordinary_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from studymate.application.ai.ports import AiExecutorStateUncertainError
    from studymate.infrastructure.ai import process

    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import time;time.sleep(30)",
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        env={"PATH": "/usr/bin:/bin"},
        start_new_session=True,
    )
    original_wait = child.wait

    async def delayed_reaping() -> int:
        await asyncio.Event().wait()
        raise RuntimeError("unreachable")

    monkeypatch.setattr(child, "wait", delayed_reaping)
    monkeypatch.setattr(process, "STOP_CONFIRM_SECONDS", 0.03)
    try:
        with pytest.raises(AiExecutorStateUncertainError, match="physical stop"):
            await preflight.stop_inspection(child)
    finally:
        # Actual signal delivery already terminated this task-owned sole child;
        # retain/reap its real wait handle even though delivery was delayed above.
        await asyncio.wait_for(original_wait(), timeout=1)
    assert child.returncode is not None
