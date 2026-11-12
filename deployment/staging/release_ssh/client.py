"""Hosted job SSH client. Private key/token never appear in argv or artifact files."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import struct
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from deployment.staging.release.native import cleanup_owned, finish_shielded
from deployment.staging.release_ssh.broker import COMMAND, Request, document, quiet_command, require

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

MAX_REPLY = 4096
SSH_SECONDS = 1260
HOST_KEY_FIELDS = 3
PRIVATE_KEY_LIMIT = 16384


def validate_material(host: str, known_hosts: str, private_key: str) -> None:
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,252}", host) is not None, "ssh_host")
    parts = known_hosts.strip().split()
    require(
        len(parts) == HOST_KEY_FIELDS and parts[0] == host and parts[1] == "ssh-ed25519",
        "exact_pinned_host_key",
    )
    blob = base64.b64decode(parts[2], validate=True)
    expected = struct.pack(">I", len(b"ssh-ed25519")) + b"ssh-ed25519" + struct.pack(">I", 32)
    require(blob.startswith(expected) and len(blob) == len(expected) + 32, "host_key_format")
    require(
        private_key.startswith("-----BEGIN OPENSSH PRIVATE KEY-----\n")
        and private_key.rstrip().endswith("-----END OPENSSH PRIVATE KEY-----")
        and len(private_key) <= PRIVATE_KEY_LIMIT,
        "private_key_format",
    )


@asynccontextmanager
async def key_agent(private: str, directory: Path) -> AsyncIterator[tuple[Path, dict[str, str]]]:
    socket = directory / "agent.sock"
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(directory),
        "SSH_AUTH_SOCK": str(socket),
        "SSH_ASKPASS_REQUIRE": "never",
    }
    creation = asyncio.create_task(
        asyncio.create_subprocess_exec(
            "/usr/bin/ssh-agent",
            "-D",
            "-a",
            str(socket),
            start_new_session=True,
            env=env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    )
    process, interrupted = await finish_shielded(creation)
    try:
        if interrupted:
            raise asyncio.CancelledError
        async with asyncio.timeout(5):
            for _ in range(400):
                if await asyncio.to_thread(socket.exists):
                    break
                await asyncio.sleep(0.01)
            else:
                raise TimeoutError("ssh_agent_start")
            require(
                await quiet_command(
                    ("/usr/bin/ssh-add", "-t", "25m", "-"), env, None, private.encode()
                )
                == 0,
                "ssh_agent_key_load",
            )
        yield socket, env
    finally:
        _, interrupted = await finish_shielded(asyncio.create_task(cleanup_owned(process)))
        if interrupted:
            raise asyncio.CancelledError


def ssh_arguments(host: str, agent: Path, known_file: Path) -> tuple[str, ...]:
    return (
        "/usr/bin/ssh",
        "-F",
        "/dev/null",
        "-T",
        "-oBatchMode=yes",
        "-oStrictHostKeyChecking=yes",
        "-oGlobalKnownHostsFile=/dev/null",
        f"-oUserKnownHostsFile={known_file}",
        "-oIdentitiesOnly=no",
        f"-oIdentityAgent={agent}",
        "-oIdentityFile=none",
        "-oForwardAgent=no",
        "-oHostKeyAlgorithms=ssh-ed25519",
        "-oPasswordAuthentication=no",
        "-oKbdInteractiveAuthentication=no",
        "-oNumberOfPasswordPrompts=0",
        "-oClearAllForwardings=yes",
        "-oRequestTTY=no",
        "-oConnectionAttempts=1",
        "-oConnectTimeout=15",
        "-oServerAliveInterval=15",
        "-oServerAliveCountMax=2",
        "-oLogLevel=ERROR",
        "peerly-release@" + host,
        COMMAND,
    )


async def exchange(
    raw: bytes, request: Request, argv: tuple[str, ...], env: dict[str, str]
) -> None:
    creation = asyncio.create_task(
        asyncio.create_subprocess_exec(
            *argv,
            start_new_session=True,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    )
    process, interrupted = await finish_shielded(creation)
    try:
        if interrupted:
            raise asyncio.CancelledError
        require(process.stdin is not None and process.stdout is not None, "ssh_pipes")
        if process.stdin is None or process.stdout is None:
            raise RuntimeError("ssh_pipes")
        async with asyncio.timeout(SSH_SECONDS):
            process.stdin.write(raw + b"\n")
            await process.stdin.drain()
            process.stdin.close()
            output = bytearray()
            while block := await process.stdout.read(MAX_REPLY + 1 - len(output)):
                output.extend(block)
                require(len(output) <= MAX_REPLY, "ssh_reply_limit")
            await process.wait()
        require(process.returncode == 0, "ssh_failed_or_unknown_no_retry")
        require(
            document(bytes(output))
            == {"protocol": 1, "outcome": "verified", "attempt": request.attempt},
            "ssh_verified_reply",
        )
    finally:
        _, interrupted = await finish_shielded(asyncio.create_task(cleanup_owned(process)))
        if interrupted:
            raise asyncio.CancelledError


async def send(raw: bytes, host: str, known: str, private: str) -> None:
    request = Request.parse(raw)
    validate_material(host, known, private)
    with tempfile.TemporaryDirectory(prefix="peerly-ssh-") as temporary:
        directory = Path(temporary)
        known_file = directory / "known_hosts"
        await asyncio.to_thread(known_file.write_text, known.strip() + "\n")
        await asyncio.to_thread(known_file.chmod, 0o600)
        async with key_agent(private, directory) as (agent, env):
            await exchange(raw, request, ssh_arguments(host, agent, known_file), env)


def main() -> int:
    try:
        raw = json.dumps(
            {
                "protocol": 1,
                "operation": os.environ["OPERATION"],
                "source_sha": os.environ["SOURCE_SHA"],
                "run_id": int(os.environ["GITHUB_RUN_ID"]),
                "run_attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]),
                "recovery_attempt": os.environ.get("RECOVERY_ATTEMPT", ""),
                "reconcile_attempt": os.environ.get("RECONCILE_ATTEMPT", ""),
                "compatible_schema": os.environ.get("COMPATIBLE_SCHEMA", ""),
                "github_token": os.environ["GITHUB_TOKEN"],
            },
            separators=(",", ":"),
        ).encode()
        asyncio.run(
            send(
                raw,
                os.environ["PEERLY_STAGING_SSH_HOST"],
                os.environ["PEERLY_STAGING_SSH_KNOWN_HOSTS"],
                os.environ["PEERLY_STAGING_SSH_PRIVATE_KEY"],
            )
        )
    except (OSError, ValueError, RuntimeError, KeyError, TimeoutError):
        sys.stderr.write("staging_ssh_failed_or_unknown_no_retry\n")
        return 1
    sys.stdout.write("staging_operation_verified\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
