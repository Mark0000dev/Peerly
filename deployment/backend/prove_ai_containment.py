"""Parent-run credential-FREE diagnostic in the exact held AI container.

Only inputs: explicit max_processes32..40 and optional reviewed RFC1918 OTLP IPv4
(port4318, TCP connect only). Never creates/updates receipts, queries SQL, performs
provider/auth calls, reads auth/config data or enables a worker. Parent alone
executes the live namespace/native checks. Unit tests substitute owned boundaries.

Use the approved final container's UID10002, read-only root, named AppArmor,
seccomp/proc policy and bounded job tmpfs. All markers/context are newly owned
synthetic files. No auth.json is created. Production LinuxSandbox, InspectionPolicy,
pinned CLI identity and physical _stop are reused, not restated as another policy.
A failed/uncertain stop retains its synthetic context for explicit parent cleanup.
No all-container/model-tool/provider acceptance is inferred from this diagnostic.
"""

import argparse
import asyncio
import hashlib
import ipaddress
import json
import os
import re
import shutil
import stat
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Never
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from studymate.infrastructure.ai.lifecycle import settle_cleanup
from studymate.infrastructure.ai.process import TerminationUncertainError
from studymate.infrastructure.ai.process import _stop as production_stop
from studymate.infrastructure.ai.runtime.acceptance import policy_digest
from studymate.infrastructure.ai.runtime.policy import (
    INSPECTED_SHA256,
    INSPECTED_VERSION,
    InspectionPolicy,
    require_max_processes,
)
from studymate.infrastructure.ai.runtime.preflight import CliInspectionError, PinnedCli
from studymate.infrastructure.ai.sandbox import FORBIDDEN_JOB_ROOTS, LinuxSandbox

CLI = Path("/usr/local/lib/peerly-codex/vendor/x86_64-unknown-linux-musl/bin/codex")
BWRAP_SHA256 = "77360cb751ccedc5971391444ac86a8a33c15b04d6b4a6fe45f5d25496e62c4c"
WORKSPACES = Path("/var/lib/peerly-ai/jobs")
UID = 10002
MEMORY = 1024 * 1024 * 1024
WORKSPACE_MAX = 64 * 1024 * 1024
CPU_MAX = "50000 100000"
OUTPUT_MAX = 65536
OPERATION_SECONDS = 12
OTLP_PORT = 4318
DRAIN_CHUNK = 4096
BINARY_MODE = 0o555
SYNTHETIC = b"PEERLY_SYNTHETIC_ONLY_NO_CREDENTIAL"
PROOF_SECONDS = 50
NAMESPACES = ("mnt", "pid", "ipc", "uts", "user", "cgroup", "net")
PRIVATE_NAMESPACES = ("mnt", "pid", "ipc", "uts", "user")
ENV_MARKER = "PEERLY_CONTAINMENT_SYNTHETIC"
PRIVATE_NETWORKS = tuple(
    ipaddress.IPv4Network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)

type FailureCode = Literal[
    "configuration",
    "controller_limits",
    "native_identity",
    "controller_otlp",
    "output_bound",
    "child_failed",
    "output_invalid",
    "deadline",
    "stop_uncertain",
    "cleanup",
    "cancelled",
]


class ProofError(Exception):
    def __init__(self, code: FailureCode) -> None:
        super().__init__(code)
        self.code = code


def require(condition: bool, code: FailureCode) -> None:
    if not condition:
        raise ProofError(code)


def otlp_address(value: str) -> str:
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError:
        raise ProofError("configuration") from None
    require(
        str(address) == value and any(address in network for network in PRIVATE_NETWORKS),
        "configuration",
    )
    return str(address)


@dataclass(frozen=True, slots=True)
class Configuration:
    max_processes: int
    otlp_ip: str | None = None
    workspaces: Path = WORKSPACES

    def __post_init__(self) -> None:
        require_max_processes(self.max_processes)
        require(
            self.workspaces.is_absolute()
            and ".." not in self.workspaces.parts
            and self.workspaces != Path("/")
            and not any(self.workspaces.is_relative_to(path) for path in FORBIDDEN_JOB_ROOTS),
            "configuration",
        )
        if self.otlp_ip is not None:
            otlp_address(self.otlp_ip)


class ChildEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, hide_input_in_errors=True)
    phase: Literal["outer", "nested"]
    private_paths_denied: Literal[True]
    marker_fd_denied: Literal[True]
    proc_escape_denied: Literal[True]
    environment_denied: Literal[True]
    private_namespaces: Literal[True]
    usr_write_denied: Literal[True]
    auth_readable: bool
    auth_writable: bool
    job_writable: bool
    transport_control: Literal["reachable", "denied"]
    otlp_control: Literal["not_requested", "reachable", "denied"]
    nproc: tuple[int, int]
    address_space: tuple[int, int]
    scratch_bytes: int | None


class Diagnostic(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    kind: Literal["credential_free_containment_diagnostic"] = (
        "credential_free_containment_diagnostic"
    )
    result: Literal["PASS", "FAIL"]
    proof_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    failure: FailureCode | None = None
    cleanup_pending: bool = False
    physical_groups_stopped: bool = False
    max_processes: int = Field(ge=32, le=40)
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    binary_sha256: str = INSPECTED_SHA256
    outer: ChildEvidence | None = None
    nested: ChildEvidence | None = None
    startup_config_valid: bool = False
    startup_config_sha256: str | None = None
    controller_otlp_positive: bool | None = None
    receipt_issued: Literal[False] = False
    provider_called: Literal[False] = False
    model_tasks_proven: Literal[False] = False
    all_model_tools_proven: Literal[False] = False
    whole_container_stopped: Literal[False] = False


# Fixed stdlib-only probe because production outer root intentionally excludes /app
# and the application virtualenv. Inputs contain only newly owned synthetic paths.
CHILD = r"""
import json,os,pathlib,resource,socket,sys
p=json.loads(sys.argv[1])
phase=p['phase']
def require(value):
 if not value:raise SystemExit(70)
def opens(path):
 try:fd=os.open(path,os.O_RDONLY|os.O_NONBLOCK)
 except OSError:return False
 else:os.close(fd);return True
def writes(path):
 try:fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 except OSError:return False
 else:
  try:os.write(fd,b'SYNTHETIC_ONLY')
  finally:os.close(fd);os.unlink(path)
  return True
def marker_fd(path):
 try:fd=os.open(path,os.O_RDONLY|os.O_NONBLOCK)
 except OSError:return False
 try:
  info=os.fstat(fd)
  return [info.st_dev,info.st_ino]==p['marker_identity']
 finally:os.close(fd)
def connects(host,port):
 try:
  with socket.create_connection((host,port),timeout=.25):return True
 except OSError:return False
paths=(p['outside_marker'],'/app','/root','/home','/run/docker.sock',
 '/var/run/docker.sock','/var/lib/peerly-ai/credentials')
for path in paths:
 require(not opens(path))
for name in ('mnt','pid','ipc','uts','user'):
 require(os.readlink('/proc/self/ns/'+name)!=p['controller_namespaces'][name])
if phase=='outer':require(os.readlink('/proc/self/ns/net')==p['controller_namespaces']['net'])
try:info=os.fstat(p['marker_fd']);inherited=[info.st_dev,info.st_ino]==p['marker_identity']
except OSError:inherited=False
require(not inherited)
require('PEERLY_CONTAINMENT_SYNTHETIC' not in os.environ)
entries=[entry for entry in pathlib.Path('/proc').iterdir() if entry.name.isdecimal()]
require(len(entries)<=p['max_processes'])
for entry in entries:
 require(not opens(str(entry)+'/root'+p['outside_marker']))
 require(not marker_fd(str(entry)+'/fd/'+str(p['marker_fd'])))
 if phase=='nested':require(not opens(str(entry)+'/root'+p['auth_marker']))
require(not opens('/proc/self/root'+p['outside_marker']))
if phase=='nested':require(not opens('/proc/self/root'+p['auth_marker']))
auth_readable=opens(p['auth_marker'])
auth_writable=writes(p['auth_write'])
job_writable=writes(p['job_write'])
require(auth_readable==(phase=='outer'))
require(auth_writable==(phase=='outer') and job_writable==(phase=='outer'))
usr_write=writes(p['usr_write'])
require(not usr_write)
nproc=resource.getrlimit(resource.RLIMIT_NPROC)
address_space=resource.getrlimit(resource.RLIMIT_AS)
require(nproc==(p['max_processes'],p['max_processes']))
require(address_space==(p['address_space'],p['address_space']))
transport=connects('127.0.0.1',p['transport_port'])
require(transport==(phase=='outer'))
otlp='not_requested'
if p['otlp_ip'] is not None:
 positive=connects(p['otlp_ip'],4318)
 require(positive==(phase=='outer'))
 otlp='reachable' if positive else 'denied'
scratch=None
if phase=='outer':
 volume=os.statvfs('/scratch');scratch=volume.f_blocks*volume.f_frsize
 require(scratch<=p['scratch_max'])
print(json.dumps({'phase':phase,'private_paths_denied':True,'marker_fd_denied':True,
 'proc_escape_denied':True,'environment_denied':True,'private_namespaces':True,
 'usr_write_denied':True,'auth_readable':auth_readable,'auth_writable':auth_writable,
 'job_writable':job_writable,'transport_control':'reachable' if transport else 'denied',
 'otlp_control':otlp,'nproc':nproc,'address_space':address_space,'scratch_bytes':scratch}))
"""


@dataclass(slots=True)
class Runner:
    configuration: Configuration
    proof_id: str = field(default_factory=lambda: uuid4().hex)
    stopped: bool = True
    context: Path | None = None
    job_directory: Path | None = None

    @property
    def cli(self) -> PinnedCli:
        return PinnedCli(CLI, INSPECTED_VERSION, INSPECTED_SHA256)

    @property
    def sandbox(self) -> LinuxSandbox:
        return LinuxSandbox(
            CLI.parent.parent / "codex-resources/bwrap",
            Path("/usr/bin/prlimit"),
            processes=self.configuration.max_processes,
            network_egress_restricted=True,
        )

    def controller(self) -> dict[str, str]:
        require(os.geteuid() == UID and os.getegid() == UID, "controller_limits")
        status = Path("/proc/self/status").read_text()
        require(
            "NoNewPrivs:\t1" in status
            and "CapEff:\t0000000000000000" in status
            and bool(os.statvfs("/").f_flag & os.ST_RDONLY),
            "controller_limits",
        )
        group = Path("/sys/fs/cgroup")
        require(
            group.joinpath("pids.max").read_text().strip() == str(self.configuration.max_processes)
            and group.joinpath("memory.max").read_text().strip() == str(MEMORY)
            and group.joinpath("cpu.max").read_text().strip() == CPU_MAX,
            "controller_limits",
        )
        root = self.configuration.workspaces
        require(not root.is_symlink() and root.resolve() == root, "controller_limits")
        volume = os.statvfs(root)
        require(
            bool(volume.f_flag & os.ST_NOEXEC)
            and volume.f_blocks * volume.f_frsize <= WORKSPACE_MAX,
            "controller_limits",
        )
        return {name: os.readlink("/proc/self/ns/" + name) for name in NAMESPACES}

    async def connect_control(self) -> bool | None:
        if self.configuration.otlp_ip is None:
            return None
        try:
            async with asyncio.timeout(1):
                _reader, writer = await asyncio.open_connection(
                    self.configuration.otlp_ip, OTLP_PORT
                )
                writer.close()
                await writer.wait_closed()
        except (OSError, TimeoutError):
            raise ProofError("controller_otlp") from None
        return True

    async def drain(self, reader: asyncio.StreamReader | None) -> bytes:
        require(reader is not None, "output_invalid")
        if reader is None:
            raise ProofError("output_invalid")
        result = bytearray()
        exceeded = False
        while chunk := await reader.read(DRAIN_CHUNK):
            if len(result) + len(chunk) <= OUTPUT_MAX and not exceeded:
                result.extend(chunk)
            else:
                exceeded = True
        require(not exceeded, "output_bound")
        return bytes(result)

    async def child(self, invocation: tuple[str, ...], job: Path, auth: Path) -> bytes:
        command = self.sandbox.command(invocation, job)
        self.stopped = False
        creation = asyncio.create_task(
            asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                close_fds=True,
                start_new_session=True,
                cwd=job,
                limit=DRAIN_CHUNK,
                env={
                    "PATH": "/usr/bin:/bin",
                    "LANG": "C.UTF-8",
                    "HOME": str(job),
                    "CODEX_HOME": str(auth),
                    "TMPDIR": "/scratch",
                },
            )
        )
        try:
            process = await asyncio.shield(creation)
        except asyncio.CancelledError:
            try:
                process = await settle_cleanup(creation)
            except OSError:
                self.stopped = True
                raise ProofError("child_failed") from None
            await self.stop(process)
            raise
        except OSError:
            self.stopped = True
            raise ProofError("child_failed") from None
        streams = [
            asyncio.create_task(self.drain(process.stdout)),
            asyncio.create_task(self.drain(process.stderr)),
        ]
        try:
            async with asyncio.timeout(OPERATION_SECONDS):
                await process.wait()
                output, _error = await asyncio.gather(*streams)
            require(process.returncode == 0, "child_failed")
            return output
        finally:
            try:
                await self.stop(process)
            finally:
                for task in streams:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*streams, return_exceptions=True)

    async def stop(self, process: asyncio.subprocess.Process) -> None:
        task = asyncio.create_task(production_stop(process))
        try:
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                await settle_cleanup(task)
                self.stopped = True
                raise
        except TerminationUncertainError:
            raise ProofError("stop_uncertain") from None
        self.stopped = True

    def prepare(self) -> tuple[Path, Path, Path]:
        context = self.configuration.workspaces / ("peerly-containment-" + self.proof_id)
        context.mkdir(mode=0o700)
        self.context = context
        # Match production mkdtemp(root, prefix="peerly-ai-")/auth exactly.
        # The unmounted control directory is a sibling, never a job ancestor.
        job = self.configuration.workspaces / ("peerly-ai-" + self.proof_id)
        job.mkdir(mode=0o700)
        self.job_directory = job
        auth = job / "auth"
        auth.mkdir(mode=0o700)
        outside = self.context / "outside-marker"
        for marker in (outside, auth / "synthetic-marker"):
            descriptor = os.open(
                marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            try:
                require(os.write(descriptor, SYNTHETIC) == len(SYNTHETIC), "configuration")
            finally:
                os.close(descriptor)
        return job, auth, outside

    async def probes(
        self, namespaces: dict[str, str], job: Path, auth: Path, outside: Path
    ) -> tuple[ChildEvidence, ChildEvidence, str]:
        python = native_python()
        descriptor = os.open(outside, os.O_RDONLY | os.O_NOFOLLOW)
        os.set_inheritable(descriptor, True)
        try:
            server = await asyncio.start_server(close_connection, "127.0.0.1", 0)
        except BaseException:
            os.close(descriptor)
            raise
        try:
            marker = os.fstat(descriptor)
            params: dict[str, object] = {
                "job": str(job),
                "auth_marker": str(auth / "synthetic-marker"),
                "outside_marker": str(outside),
                "auth_write": str(auth / "synthetic-refresh"),
                "job_write": str(job / "synthetic-write"),
                "usr_write": "/usr/peerly-proof-" + self.proof_id,
                "marker_fd": descriptor,
                "marker_identity": [marker.st_dev, marker.st_ino],
                "controller_namespaces": namespaces,
                "max_processes": self.configuration.max_processes,
                "address_space": self.sandbox.address_space_bytes,
                "scratch_max": self.sandbox.temporary_bytes,
                "transport_port": server.sockets[0].getsockname()[1],
                "otlp_ip": self.configuration.otlp_ip,
            }
            outer = await self.child(
                (str(python), "-c", CHILD, json.dumps(params | {"phase": "outer"})), job, auth
            )
            policy = InspectionPolicy(job, auth, self.configuration.max_processes).overrides(
                self.cli
            )
            nested = await self.child(
                (
                    str(CLI),
                    "sandbox",
                    "--permission-profile",
                    "peerly",
                    "-C",
                    str(job),
                    *policy,
                    "--",
                    str(python),
                    "-c",
                    CHILD,
                    json.dumps(params | {"phase": "nested"}),
                ),
                job,
                auth,
            )
            startup = await self.child(
                (str(CLI), "app-server", "--print-startup-config", "--strict-config", *policy),
                job,
                auth,
            )
            try:
                outer_evidence = self.evidence(outer, "outer")
                nested_evidence = self.evidence(nested, "nested")
                require(bool(startup.strip()), "output_invalid")
                return outer_evidence, nested_evidence, hashlib.sha256(startup).hexdigest()
            except ValidationError:
                raise ProofError("output_invalid") from None
        finally:
            server.close()
            try:
                await server.wait_closed()
            finally:
                os.close(descriptor)

    def evidence(self, data: bytes, phase: Literal["outer", "nested"]) -> ChildEvidence:
        evidence = ChildEvidence.model_validate_json(data)
        positive = phase == "outer"
        expected_otlp = (
            ("reachable" if positive else "denied")
            if self.configuration.otlp_ip
            else "not_requested"
        )
        require(
            evidence.phase == phase
            and evidence.auth_readable == positive
            and evidence.auth_writable == positive
            and evidence.job_writable == positive
            and evidence.transport_control == ("reachable" if positive else "denied")
            and evidence.otlp_control == expected_otlp
            and evidence.nproc == (self.configuration.max_processes,) * 2
            and evidence.address_space == (self.sandbox.address_space_bytes,) * 2,
            "output_invalid",
        )
        require(
            (
                evidence.scratch_bytes is not None
                and 0 < evidence.scratch_bytes <= self.sandbox.temporary_bytes
            )
            if positive
            else evidence.scratch_bytes is None,
            "output_invalid",
        )
        return evidence

    async def verify_identity(self) -> None:
        await self.cli.verify()
        bwrap = self.sandbox.bubblewrap
        require(
            not bwrap.is_symlink()
            and stat.S_IMODE(bwrap.stat().st_mode) == BINARY_MODE
            and hashlib.sha256(bwrap.read_bytes()).hexdigest() == BWRAP_SHA256,
            "native_identity",
        )

    async def run(self) -> Diagnostic:
        require(re.fullmatch(r"[0-9a-f]{32}", self.proof_id) is not None, "configuration")
        outer: ChildEvidence | None = None
        nested: ChildEvidence | None = None
        config_sha: str | None = None
        otlp: bool | None = None
        failure: FailureCode | None = None
        try:
            async with asyncio.timeout(PROOF_SECONDS):
                namespaces = self.controller()
                await self.verify_identity()
                otlp = await self.connect_control()
                job, auth, outside = self.prepare()
                require(ENV_MARKER not in os.environ, "configuration")
                os.environ[ENV_MARKER] = "SYNTHETIC_ONLY"
                try:
                    version = await self.child((str(CLI), "--version"), job, auth)
                    require(version.strip() == INSPECTED_VERSION.encode(), "native_identity")
                    outer, nested, config_sha = await self.probes(namespaces, job, auth, outside)
                finally:
                    os.environ.pop(ENV_MARKER, None)
        except CliInspectionError:
            failure = "native_identity"
        except ProofError as error:
            failure = error.code
        except TimeoutError:
            failure = "deadline"
        except asyncio.CancelledError:
            failure = "cancelled"
        except (OSError, ValueError):
            failure = "configuration"
        owned_directories = (self.job_directory, self.context)
        if self.stopped:
            for directory in owned_directories:
                if directory is not None:
                    try:
                        shutil.rmtree(directory)
                    except OSError:
                        failure = "cleanup"
        pending = any(
            directory is not None and directory.exists() for directory in owned_directories
        )
        return Diagnostic(
            result="PASS" if failure is None else "FAIL",
            proof_id=self.proof_id,
            failure=failure,
            cleanup_pending=pending,
            physical_groups_stopped=self.stopped,
            max_processes=self.configuration.max_processes,
            policy_sha256=policy_digest(self.cli, max_processes=self.configuration.max_processes),
            outer=outer,
            nested=nested,
            startup_config_valid=config_sha is not None,
            startup_config_sha256=config_sha,
            controller_otlp_positive=otlp,
        )


def native_python() -> Path:
    executable = Path(sys.executable).resolve()
    require(executable.is_relative_to("/usr"), "configuration")
    return executable


def close_connection(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    writer.close()


class ClosedParser(argparse.ArgumentParser):
    def error(self, _message: str) -> Never:
        raise ProofError("configuration")


async def main_async() -> int:
    parser = ClosedParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--max-processes", type=int, required=True)
    parser.add_argument("--otlp-ip")
    try:
        args = parser.parse_args()
        result = await Runner(Configuration(args.max_processes, args.otlp_ip)).run()
    except (ValueError, ProofError):
        sys.stdout.write(
            json.dumps(
                {
                    "kind": "credential_free_containment_diagnostic",
                    "result": "FAIL",
                    "failure": "configuration",
                    "receipt_issued": False,
                }
            )
            + "\n"
        )
        return 1
    sys.stdout.write(result.model_dump_json() + "\n")
    return 0 if result.result == "PASS" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async()))
