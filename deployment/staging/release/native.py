"""Native Compose renderer with private input, fixed argv and bounded lifetime."""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from deployment.staging.release.data import Object, load, require

if TYPE_CHECKING:
    from deployment.staging.release.release import Snapshot


COMPOSE_SECONDS = 20
TERM_GRACE = 0.2
REAP_SECONDS = 2.0


@dataclass(frozen=True, slots=True)
class OwnedResult:
    stdout: bytes
    returncode: int


async def finish_shielded[T](task: asyncio.Task[T]) -> tuple[T, bool]:
    interrupted = False
    while True:
        try:
            return await asyncio.shield(task), interrupted
        except asyncio.CancelledError:
            if task.cancelled():
                raise
            interrupted = True


def signal_group(pid: int, sig: signal.Signals) -> bool:
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        return False
    return True


async def cleanup_owned(process: asyncio.subprocess.Process) -> None:
    # The group was created solely for this command. Descendants that remain in
    # that owned session are signalled even if the direct parent already exited.
    if signal_group(process.pid, signal.SIGTERM):
        await asyncio.sleep(TERM_GRACE)
        signal_group(process.pid, signal.SIGKILL)
    async with asyncio.timeout(REAP_SECONDS):
        await process.wait()


async def owned_command(
    argv: tuple[str, ...],
    *,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
) -> OwnedResult:
    creation = asyncio.create_task(
        asyncio.create_subprocess_exec(
            *argv,
            start_new_session=True,
            env=env,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    )
    # Shield creation too: cancellation between fork and transport setup must
    # still obtain the owned PID and clean it before returning cancellation.
    process, interrupted = await finish_shielded(creation)
    cancellation: asyncio.CancelledError | None = None
    try:
        if interrupted:
            raise asyncio.CancelledError
        stdout, _ = await process.communicate()
        require(process.returncode is not None, "owned_process_not_reaped")
        if process.returncode is None:
            raise RuntimeError("owned_process_not_reaped")
        return OwnedResult(stdout, process.returncode)
    except asyncio.CancelledError as error:
        cancellation = error
        raise
    finally:
        try:
            _, cancelled_during_cleanup = await finish_shielded(
                asyncio.create_task(cleanup_owned(process))
            )
        except (OSError, TimeoutError) as error:
            if cancellation is not None:
                raise cancellation from error
            raise
        if cancelled_during_cleanup:
            raise asyncio.CancelledError


async def render_native(snapshot: Snapshot) -> Object:
    docker = shutil.which("docker")
    require(docker is not None and os.path.isabs(docker), "compose_executable")
    if docker is None:
        raise RuntimeError("compose_executable")
    with tempfile.TemporaryDirectory(prefix="peerly-compose-") as directory:
        path = Path(directory) / "compose.yml"
        path.write_text(snapshot.content)
        path.chmod(0o600)
        env = {"PATH": "/usr/bin:/usr/local/bin:/bin", **snapshot.env()}
        require(
            not any(k.startswith(("COMPOSE_", "DOCKER_")) for k in snapshot.env()),
            "ambient_compose_override",
        )
        async with asyncio.timeout(COMPOSE_SECONDS):
            result = await owned_command(
                (
                    docker,
                    "compose",
                    "--project-name",
                    "peerly-staging",
                    "--env-file",
                    "/dev/null",
                    "--file",
                    str(path),
                    "config",
                    "--format",
                    "json",
                ),
                env=env,
                cwd=directory,
            )
        require(result.returncode == 0, "native_compose_validation")
        return load(result.stdout)
