"""Synthetic cache positive controls and actual CLI command-path bypass attempts."""

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path

from studymate.infrastructure.ai.runtime.preflight import (
    CliInspectionError,
    PinnedCli,
    inspect_command,
)

POSITIVE = """
import os, pathlib, sys
path = pathlib.Path(sys.argv[1])
assert path.read_bytes().startswith(b'SYNTHETIC_')
following = path.with_name('synthetic-refresh')
with following.open('xb') as target:
    target.write(b'SYNTHETIC_REFRESH_NOT_A_CREDENTIAL')
    target.flush()
    os.fsync(target.fileno())
os.replace(following, path)
assert path.read_bytes() == b'SYNTHETIC_REFRESH_NOT_A_CREDENTIAL'
print('synthetic transport read/write confirmed')
"""
ATTEMPTS = """
import json, os, pathlib, sys
values = json.loads(sys.argv[1])
for path in values['paths']:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    except OSError:
        pass
    else:
        os.close(fd)
        raise SystemExit(11)
for flags, path in ((os.O_WRONLY | os.O_TRUNC, values['marker']),
                    (os.O_WRONLY | os.O_CREAT | os.O_EXCL, values['new_file'])):
    try:
        fd = os.open(path, flags, 0o600)
    except OSError:
        pass
    else:
        os.close(fd)
        raise SystemExit(12)
for candidate in pathlib.Path('/proc/self/fd').iterdir():
    if int(candidate.name) <= 2:
        continue
    try:
        info = os.fstat(int(candidate.name))
    except OSError:
        continue
    if [info.st_dev, info.st_ino] == values['identity']:
        raise SystemExit(13)
print(json.dumps({'read_aliases_denied':True,'cache_writes_denied':True,'marker_fd_denied':True}))
"""


@dataclass(frozen=True, slots=True)
class AuthBoundaryEvidence:
    transport_read_write: bool
    read_aliases_denied: bool
    cache_writes_denied: bool
    marker_fd_denied: bool
    all_model_tools_proven: bool = False
    real_credential_refresh_proven: bool = False


async def prove_cli_auth_aliases(cli: PinnedCli, job: Path, marker: Path) -> AuthBoundaryEvidence:
    if not marker.is_relative_to(job) or marker.parent == job:
        raise ValueError("Synthetic cache must be in a private child directory")
    await cli.verify()
    positive = await inspect_command(
        ("/usr/bin/python3", "-c", POSITIVE, str(marker)), dedicated_home=job
    )
    if positive.exit_code:
        raise CliInspectionError("transport_positive_control")
    alias = job / "synthetic-public-link"
    await asyncio.to_thread(alias.symlink_to, marker)
    descriptor = await asyncio.to_thread(os.open, marker, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.set_inheritable(descriptor, True)
        metadata = os.fstat(descriptor)
        arguments = json.dumps(
            {
                "marker": str(marker),
                "new_file": str(marker.parent / "synthetic-unapproved-write"),
                "paths": [
                    str(marker),
                    str(alias),
                    "/proc/self/root" + str(marker),
                    f"/proc/{os.getpid()}/root{marker}",
                    f"/proc/{os.getpid()}/fd/{descriptor}",
                ],
                "identity": [metadata.st_dev, metadata.st_ino],
            }
        )
        profile = (
            'permissions.peerly.filesystem={":minimal"="read",'
            + json.dumps(str(job))
            + '="read",'
            + json.dumps(str(marker.parent))
            + '="deny",'
            + json.dumps(str(job / "empty-auth"))
            + '="deny","/home"="deny","/root"="deny"}'
        )
        result = await inspect_command(
            (
                str(cli.executable),
                "sandbox",
                "--permission-profile",
                "peerly",
                "-C",
                str(job),
                "-c",
                profile,
                "-c",
                "permissions.peerly.network.enabled=false",
                "--",
                "/usr/bin/python3",
                "-c",
                ATTEMPTS,
                arguments,
            ),
            dedicated_home=job,
        )
    finally:
        os.close(descriptor)
        await asyncio.to_thread(alias.unlink)
    if result.exit_code:
        raise CliInspectionError("cli_auth_alias_denial")
    try:
        value = json.loads(result.stdout)
    except ValueError:
        raise CliInspectionError("cli_auth_alias_output") from None
    if value != {
        "read_aliases_denied": True,
        "cache_writes_denied": True,
        "marker_fd_denied": True,
    }:
        raise CliInspectionError("cli_auth_alias_output")
    return AuthBoundaryEvidence(True, True, True, True)
