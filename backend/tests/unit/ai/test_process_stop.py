"""Physical-stop races: leader completion and group reaping have one hard deadline."""

import asyncio
import signal
import sys
from pathlib import Path

import pytest

from studymate.domain.ai.tasks import ClarifiedGoal
from studymate.infrastructure.ai import process
from studymate.infrastructure.ai.process import TerminationUncertainError
from tests.unit.ai.test_process import executor, task

GROUP_REAP_OBSERVATIONS = 3
STOP_WAIT_PHASES = 2


async def exited_leader() -> asyncio.subprocess.Process:
    leader = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "pass",
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert await leader.wait() == 0
    return leader


async def test_sigkill_group_reaping_is_awaited_after_leader_already_exited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    leader = await exited_leader()
    reaper_scheduled = asyncio.Event()
    observations = 0

    def group_exists(pid: int) -> bool:
        nonlocal observations
        assert pid == leader.pid
        observations += 1
        if observations == 1:
            asyncio.get_running_loop().call_soon(reaper_scheduled.set)
        else:
            assert reaper_scheduled.is_set()
        return observations < GROUP_REAP_OBSERVATIONS

    monkeypatch.setattr(process, "_group_exists", group_exists)
    await process._stop(leader)
    assert observations == GROUP_REAP_OBSERVATIONS


async def test_never_disappearing_group_exhausts_shared_deadline_as_uncertainty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    leader = await exited_leader()
    monkeypatch.setattr(process, "STOP_CONFIRM_SECONDS", 0.03)
    monkeypatch.setattr(process, "_group_exists", lambda _pid: True)
    with pytest.raises(TerminationUncertainError, match="physical stop") as failure:
        await process._stop(leader)
    assert isinstance(failure.value.__cause__, TimeoutError)


async def test_leader_and_group_waits_use_the_same_absolute_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    leader = await exited_leader()
    deadlines: list[float | None] = []
    actual_timeout = asyncio.timeout_at

    def observed_timeout(when: float | None) -> asyncio.Timeout:
        deadlines.append(when)
        return actual_timeout(when)

    monkeypatch.setattr(process, "STOP_CONFIRM_SECONDS", 0.03)
    monkeypatch.setattr(process, "_group_exists", lambda _pid: True)
    monkeypatch.setattr(asyncio, "timeout_at", observed_timeout)
    with pytest.raises(TerminationUncertainError, match="physical stop"):
        await process._stop(leader)
    assert len(deadlines) == STOP_WAIT_PHASES
    assert deadlines[0] == deadlines[1]


async def test_signal_failure_never_claims_a_confirmed_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    leader = await exited_leader()

    def refused(pid: int, sig: signal.Signals) -> None:
        assert pid == leader.pid
        assert sig == signal.SIGTERM
        raise PermissionError("Controlled signal refusal")

    monkeypatch.setattr(process, "_signal_group", refused)
    with pytest.raises(TerminationUncertainError, match="physical stop") as failure:
        await process._stop(leader)
    assert isinstance(failure.value.__cause__, PermissionError)


async def test_stop_leader_wait_timeout_preserves_workspace_instead_of_retryable_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = await executor(tmp_path, 'result.write_text(\'{"suggestion":"Synthetic advice"}\')')
    killed: set[int] = set()
    actual_wait = asyncio.subprocess.Process.wait
    actual_signal = process._signal_group

    def observe_kill(pid: int, sig: signal.Signals) -> None:
        actual_signal(pid, sig)
        if sig == signal.SIGKILL:
            killed.add(pid)

    async def stuck_wait(leader: asyncio.subprocess.Process) -> int:
        if leader.pid in killed:
            await asyncio.Event().wait()
            return 0
        return await actual_wait(leader)

    monkeypatch.setattr(process, "STOP_CONFIRM_SECONDS", 0.03)
    monkeypatch.setattr(process, "_signal_group", observe_kill)
    monkeypatch.setattr(asyncio.subprocess.Process, "wait", stuck_wait)
    with pytest.raises(TerminationUncertainError, match="physical stop"):
        await adapter.execute(task(), 2)
    assert list(adapter.configuration.temporary_root.iterdir())


async def test_version_cleanup_race_does_not_prevent_typed_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = await executor(tmp_path, 'result.write_text(\'{"suggestion":"Synthetic advice"}\')')
    groups: dict[int, int] = {}

    def asynchronous_disappearance(pid: int) -> bool:
        groups[pid] = groups.get(pid, 0) + 1
        return groups[pid] == 1

    monkeypatch.setattr(process, "_group_exists", asynchronous_disappearance)
    assert await adapter.execute(task(), 2) == ClarifiedGoal("Synthetic advice")
    assert not list(adapter.configuration.temporary_root.iterdir())
