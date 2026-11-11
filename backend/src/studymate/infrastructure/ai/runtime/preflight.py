"""Pinned real CLI inspection without authentication, model execution or provider network."""

import asyncio
import hashlib
import os
import re
import signal
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from studymate.application.ai.ports import AiExecutorStateUncertainError
from studymate.infrastructure.ai.lifecycle import settle_cleanup
from studymate.infrastructure.ai.runtime.namespace import OfflineNamespace

MAX_INSPECTION_BYTES = 65_536
INSPECTION_SECONDS = 10


class CliInspectionError(Exception):
    """Finite failure; never attach raw CLI/config/file output to ordinary telemetry."""


@dataclass(frozen=True, slots=True)
class PinnedCli:
    executable: Path
    version: str
    sha256: str

    def __post_init__(self) -> None:
        if (
            not self.executable.is_absolute()
            or not self.executable.is_relative_to("/usr")
            or ".." in self.executable.parts
            or re.fullmatch(r"[0-9a-f]{64}", self.sha256) is None
            or re.fullmatch(r"codex-cli [0-9]+\.[0-9]+\.[0-9]+", self.version) is None
        ):
            raise ValueError("Native /usr executable with exact version and digest required")

    async def verify(self) -> None:
        def digest() -> str:
            if self.executable.resolve() != self.executable or not self.executable.is_file():
                raise CliInspectionError("cli_identity")
            with self.executable.open("rb") as source:
                return hashlib.file_digest(source, "sha256").hexdigest()

        try:
            actual = await asyncio.to_thread(digest)
        except OSError:
            raise CliInspectionError("cli_identity") from None
        if actual != self.sha256:
            raise CliInspectionError("cli_identity")


@dataclass(frozen=True, slots=True)
class InspectionOutput:
    exit_code: int
    stdout: bytes
    stderr: bytes


async def inspect_command(
    argv: tuple[str, ...],
    *,
    synthetic_environment_marker: bool = False,
    dedicated_home: Path | None = None,
) -> InspectionOutput:
    """Only offline namespace/help/config calls; bounded drain and kill/reap on cancellation."""
    environment = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
    if dedicated_home is not None:
        if (
            not dedicated_home.is_absolute()
            or ".." in dedicated_home.parts
            or any(dedicated_home.is_relative_to(root) for root in ("/home", "/root"))
        ):
            raise ValueError("Dedicated non-home inspection directory required")
        environment.update(
            HOME=str(dedicated_home),
            CODEX_HOME=str(dedicated_home / "empty-auth"),
            TMPDIR=str(dedicated_home),
        )
    if synthetic_environment_marker:
        environment["PEERLY_SYNTHETIC_MARKER"] = "SYNTHETIC_MARKER_NOT_A_CREDENTIAL"
    creation = asyncio.create_task(
        asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=environment,
            close_fds=True,
            start_new_session=True,
        )
    )
    try:
        process = await asyncio.shield(creation)
    except asyncio.CancelledError:
        process = await settle_cleanup(creation)
        cleanup = asyncio.create_task(stop_inspection(process))
        await settle_cleanup(cleanup)
        raise

    async def drain(reader: asyncio.StreamReader | None) -> bytes:
        if reader is None:
            raise CliInspectionError("cli_stream")
        result = bytearray()
        exceeded = False
        while value := await reader.read(4096):
            if len(result) + len(value) > MAX_INSPECTION_BYTES:
                exceeded = True
            elif not exceeded:
                result.extend(value)
        if exceeded:
            raise CliInspectionError("cli_output_bound")
        return bytes(result)

    stdout, stderr = (
        asyncio.create_task(drain(process.stdout)),
        asyncio.create_task(drain(process.stderr)),
    )
    try:
        async with asyncio.timeout(INSPECTION_SECONDS):
            streams = await asyncio.gather(stdout, stderr, process.wait())
        if process.returncode is None:
            raise CliInspectionError("cli_exit")
        return InspectionOutput(process.returncode, streams[0], streams[1])
    finally:
        cleanup = asyncio.create_task(stop_inspection(process))
        try:
            await asyncio.shield(cleanup)
        except asyncio.CancelledError:
            await settle_cleanup(cleanup)
            raise
        finally:
            await asyncio.gather(stdout, stderr, return_exceptions=True)


async def stop_inspection(process: asyncio.subprocess.Process) -> None:
    with suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)
    async with asyncio.timeout(5):
        await process.wait()
    try:
        os.killpg(process.pid, 0)
    except ProcessLookupError:
        return
    raise AiExecutorStateUncertainError("Offline inspection process group remains occupied")


@dataclass(frozen=True, slots=True)
class CliPreflight:
    cli: PinnedCli
    namespace: OfflineNamespace

    async def version(self, job: Path) -> None:
        await self.cli.verify()
        result = await inspect_command(
            self.namespace.command(job, (str(self.cli.executable), "--version"))
        )
        if result.exit_code or result.stdout.strip() != self.cli.version.encode():
            raise CliInspectionError("cli_version")

    async def configuration(self, job: Path, overrides: tuple[str, ...]) -> InspectionOutput:
        await self.cli.verify()
        arguments = (
            str(self.cli.executable),
            "app-server",
            "--print-startup-config",
            "--strict-config",
            *overrides,
        )
        return await inspect_command(self.namespace.command(job, arguments))
