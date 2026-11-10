"""Actual pinned CLI sandbox helper proof; no claim that every model tool uses it."""

import json
from dataclasses import dataclass
from pathlib import Path

from studymate.infrastructure.ai.runtime.preflight import (
    CliInspectionError,
    PinnedCli,
    inspect_command,
)

DENIAL = """
import json, os, sys
path = sys.argv[1]
try:
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
except OSError:
    print(json.dumps({'helper_auth_path_denied': True}))
else:
    os.close(descriptor)
    raise SystemExit(11)
"""


@dataclass(frozen=True, slots=True)
class ToolPermissionEvidence:
    helper_auth_path_denied: bool
    all_model_tools_proven: bool = False


async def prove_cli_read_denial(
    cli: PinnedCli, job: Path, synthetic_marker: Path
) -> ToolPermissionEvidence:
    """Explicit synthetic path is transport-readable, then denied by actual CLI sandbox."""
    if not synthetic_marker.is_relative_to(job) or synthetic_marker.parent == job:
        raise ValueError("Synthetic marker needs a private child directory inside job")
    await cli.verify()
    # The positive control matters: absence of the marker is not denial evidence.
    positive = await inspect_command(
        (
            "/usr/bin/python3",
            "-c",
            "import os,sys;fd=os.open(sys.argv[1],os.O_RDONLY);os.close(fd)",
            str(synthetic_marker),
        ),
        dedicated_home=job,
    )
    if positive.exit_code:
        raise CliInspectionError("synthetic_marker_positive_control")
    filesystem = (
        'permissions.peerly.filesystem={":minimal"="read",'
        + json.dumps(str(job))
        + '="read",'
        + json.dumps(str(synthetic_marker.parent))
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
            filesystem,
            "-c",
            "permissions.peerly.network.enabled=false",
            "--",
            "/usr/bin/python3",
            "-c",
            DENIAL,
            str(synthetic_marker),
        ),
        dedicated_home=job,
    )
    if result.exit_code:
        raise CliInspectionError("cli_helper_denial_failed")
    try:
        value = json.loads(result.stdout)
    except ValueError:
        raise CliInspectionError("cli_helper_denial_output") from None
    if value != {"helper_auth_path_denied": True}:
        raise CliInspectionError("cli_helper_denial_output")
    return ToolPermissionEvidence(True)
