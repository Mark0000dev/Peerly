"""No target host or provider calls: rejection ordering and owned dummy process."""

from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import TYPE_CHECKING

import pytest
from deployment.staging.release_ssh import broker
from deployment.staging.release_ssh.tests.test_admission import SHA, body, request

if TYPE_CHECKING:
    from pathlib import Path


class RejectedSource(broker.Github):
    async def main_sha(self) -> str:
        return SHA

    async def admit_run(self, _request: broker.Request, _tool_sha: str) -> str:
        return "Mark0000dev"

    async def fetch_tool(self, _sha: str, _destination: Path) -> None:
        raise broker.AdmissionError("synthetic_hash_mismatch")


@pytest.mark.asyncio
async def test_no_secret_load_or_execution_before_main_hash_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await asyncio.to_thread((tmp_path / "tmp").mkdir)
    monkeypatch.setattr(broker, "WORK_ROOT", tmp_path)
    monkeypatch.setattr(broker, "Github", RejectedSource)

    def forbidden(_path: Path) -> dict[str, object]:
        pytest.fail("provider inputs must not be read before hash verification")

    monkeypatch.setattr(broker, "root_document", forbidden)
    with pytest.raises(broker.AdmissionError, match="synthetic_hash_mismatch"):
        await broker.worker(request(body()))


def wait_pid(path: Path) -> int:
    end = time.monotonic() + 3
    while not path.exists():
        if time.monotonic() > end:
            raise TimeoutError("dummy_start")
        time.sleep(0.005)
    return int(path.read_text())


@pytest.mark.asyncio
async def test_gateway_owned_command_cleans_cancelled_process(tmp_path: Path) -> None:
    record = tmp_path / "pid"
    program = (
        "import os,signal,time;from pathlib import Path;"
        "signal.signal(signal.SIGTERM,signal.SIG_IGN);"
        f"Path({str(record)!r}).write_text(str(os.getpid()));time.sleep(60)"
    )
    task = asyncio.create_task(broker.quiet_command((sys.executable, "-c", program), {}, None))
    try:
        pid = await asyncio.to_thread(wait_pid, record)
        assert os.getpgid(pid) == pid
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
