"""Synthetic marker denial in a real offline namespace; not CLI tool-routing acceptance."""

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path

from studymate.infrastructure.ai.runtime.namespace import OfflineNamespace
from studymate.infrastructure.ai.runtime.preflight import CliInspectionError, inspect_command

PROBE = """
import json, os, pathlib, socket, sys
values = json.loads(sys.argv[1])
for path in values['private_paths']:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    except OSError:
        pass
    else:
        os.close(descriptor)
        raise SystemExit(11)
for path in ('/home', '/root', '/var/run/docker.sock', '/run/docker.sock'):
    if pathlib.Path(path).exists():
        raise SystemExit(12)
if 'PEERLY_SYNTHETIC_MARKER' in os.environ:
    raise SystemExit(13)
try:
    os.fstat(values['private_fd'])
except OSError:
    pass
else:
    raise SystemExit(14)
for name, identity in values['host_namespaces'].items():
    if os.readlink('/proc/self/ns/' + name) == identity:
        raise SystemExit(15)
try:
    with socket.create_connection(('127.0.0.1', values['host_port']), timeout=.2):
        raise SystemExit(16)
except OSError:
    pass
print(json.dumps({'marker_denied': True, 'environment_denied': True,
 'descriptor_denied': True, 'private_namespaces': True, 'host_network_denied': True}))
"""


@dataclass(frozen=True, slots=True)
class NamespaceEvidence:
    marker_denied: bool
    environment_denied: bool
    descriptor_denied: bool
    private_namespaces: bool
    host_network_denied: bool
    cli_tool_routing_proven: bool = False
    aggregate_cgroup_proven: bool = False


async def prove_offline_namespace(
    namespace: OfflineNamespace, job: Path, private_marker: Path
) -> NamespaceEvidence:
    """Caller creates an explicit SYNTHETIC marker outside job, never real auth."""
    if private_marker.is_relative_to(job) or not private_marker.is_absolute():
        raise ValueError("Synthetic marker must remain outside the disposable job mount")
    namespaces = {
        name: await asyncio.to_thread(os.readlink, f"/proc/self/ns/{name}")
        for name in ("mnt", "pid", "net", "ipc", "uts", "user")
    }
    server = await asyncio.start_server(lambda _reader, writer: writer.close(), "127.0.0.1", 0)
    try:
        port = server.sockets[0].getsockname()[1]
        descriptor = await asyncio.to_thread(os.open, private_marker, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            # Deliberately inheritable marker FD is still closed by subprocess boundary.
            os.set_inheritable(descriptor, True)
            arguments = json.dumps(
                {
                    "private_paths": [
                        str(private_marker),
                        "/auth/auth.json",
                        "/credentials/auth.json",
                    ],
                    "private_fd": descriptor,
                    "host_namespaces": namespaces,
                    "host_port": port,
                }
            )
            result = await inspect_command(
                namespace.command(job, ("/usr/bin/python3", "-c", PROBE, arguments)),
                synthetic_environment_marker=True,
            )
        finally:
            os.close(descriptor)
    finally:
        server.close()
        await server.wait_closed()
    if result.exit_code:
        raise CliInspectionError("namespace_denial_failed")
    try:
        value = json.loads(result.stdout)
    except ValueError:
        raise CliInspectionError("namespace_probe_output") from None
    expected = {
        "marker_denied": True,
        "environment_denied": True,
        "descriptor_denied": True,
        "private_namespaces": True,
        "host_network_denied": True,
    }
    if value != expected:
        raise CliInspectionError("namespace_probe_output")
    return NamespaceEvidence(**expected)
