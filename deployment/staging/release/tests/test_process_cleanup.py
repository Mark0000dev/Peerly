"""Real owned dummy process trees; no Docker, provider or target-host operations."""

from __future__ import annotations

import asyncio
import ctypes
import json
import os
import shutil
import signal
import sys
import time
from contextlib import suppress
from typing import TYPE_CHECKING

import pytest
from deployment.staging.release import native, publication
from deployment.staging.release.data import integer, rows
from deployment.staging.release.release import Snapshot

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

PR_SET_CHILD_SUBREAPER = 36
PR_GET_CHILD_SUBREAPER = 37
DUMMY = """import json,os,signal,subprocess,sys,time
from pathlib import Path
signal.signal(signal.SIGTERM,signal.SIG_IGN)
code=("import signal,time;from pathlib import Path;"
      "signal.signal(signal.SIGTERM,signal.SIG_IGN);Path("
      +repr(sys.argv[2])+").write_text('ready');time.sleep(60)")
child=subprocess.Popen([sys.executable,'-c',code])
while not Path(sys.argv[2]).exists():time.sleep(0.005)
Path(sys.argv[1]).write_text(json.dumps([os.getpid(),child.pid]))
time.sleep(60)
"""


@pytest.fixture
def adopt_owned_orphans() -> Iterator[None]:
    # Only this isolated pytest interpreter changes its adoption policy, never
    # host init or another process. This lets the test reap its own grandchild
    # instead of relying on the tool container's PID1 zombie-reaping behavior.
    libc = ctypes.CDLL(None, use_errno=True)
    prctl = libc.prctl
    prctl.restype = ctypes.c_int
    previous = ctypes.c_int()
    assert prctl(PR_GET_CHILD_SUBREAPER, ctypes.byref(previous), 0, 0, 0) == 0
    assert prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) == 0
    try:
        yield
    finally:
        assert prctl(PR_SET_CHILD_SUBREAPER, previous.value, 0, 0, 0) == 0


def ready(path: Path) -> tuple[int, int]:
    deadline = time.monotonic() + 3
    while not path.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError("dummy_start_deadline")
        time.sleep(0.005)
    raw: object = json.loads(path.read_bytes())
    parent, grandchild = [integer(value) for value in rows(raw)]
    return parent, grandchild


async def run_consumer(record: Path, consumer: str) -> object:
    if consumer == "publication":
        return await publication.inspect_image(str(record))
    snapshot = Snapshot({"Env": [{"name": "DUMMY_RECORD", "value": str(record)}]}, "synthetic")
    return await native.render_native(snapshot)


async def reap_adopted(pid: int) -> None:
    async with asyncio.timeout(2):
        while True:
            found, _ = await asyncio.to_thread(os.waitpid, pid, os.WNOHANG)
            if found == pid:
                return
            await asyncio.sleep(0.005)


@pytest.mark.asyncio
@pytest.mark.usefixtures("adopt_owned_orphans")
@pytest.mark.parametrize("mode", ["timeout", "cancel", "repeat_cancel"])
@pytest.mark.parametrize("consumer", ["publication", "native"])
async def test_owned_tree_killed_reaped_and_unrelated_session_survives(
    tmp_path: Path, mode: str, consumer: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = tmp_path / "pids"
    shim = tmp_path / "docker"
    program = (
        "#!" + sys.executable + "\nimport os,sys\n"
        "record=os.environ.get('DUMMY_RECORD',sys.argv[-1])\n"
        "sys.argv=[sys.argv[0],record,record+'.ready']\n" + DUMMY
    )
    compile(program, "<owned-dummy-executable>", "exec")
    await asyncio.to_thread(shim.write_text, program)
    await asyncio.to_thread(shim.chmod, 0o700)
    monkeypatch.setattr(shutil, "which", lambda _name: str(shim))
    limit = 1 if mode == "timeout" else 10
    monkeypatch.setattr(native, "COMPOSE_SECONDS", limit)
    monkeypatch.setattr(publication, "INSPECT_SECONDS", limit)
    sibling = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "import time;time.sleep(60)", start_new_session=True
    )
    task = asyncio.create_task(run_consumer(record, consumer))
    parent = grandchild = 0
    try:
        parent, grandchild = await asyncio.to_thread(ready, record)
        assert os.getpgid(parent) == parent
        assert os.getpgid(grandchild) == parent
        if mode == "timeout":
            with pytest.raises(TimeoutError):
                await task
        else:
            task.cancel()
            if mode == "repeat_cancel":
                await asyncio.sleep(0.03)
                task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        # The helper reaps its direct child; this test subreaper reaps the adopted
        # grandchild. Both ignored TERM, so group-wide KILL was necessary.
        with pytest.raises(ChildProcessError):
            await asyncio.to_thread(os.waitpid, parent, os.WNOHANG)
        await reap_adopted(grandchild)
        with pytest.raises(ProcessLookupError):
            os.kill(parent, 0)
        with pytest.raises(ProcessLookupError):
            os.kill(grandchild, 0)
        assert sibling.returncode is None
        os.kill(sibling.pid, 0)
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        if parent:
            with suppress(ProcessLookupError):
                os.killpg(parent, signal.SIGKILL)
        if grandchild:
            with suppress(ChildProcessError):
                await reap_adopted(grandchild)
        sibling.terminate()
        await sibling.wait()
