"""Root-installed, stdlib-only forced-command broker; never execute caller code."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import http.client
import json
import os
import re
import signal
import stat
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = "/repos/Mark0000dev/Peerly"
COMMAND = "peerly-staging-release-v1"
MANIFEST = "deployment/staging/release_ssh/approved-tool-files.json"
TOOL_NAMES = (
    "__init__.py",
    "bootstrap.py",
    "cli.py",
    "data.py",
    "external.py",
    "external_lifecycle.py",
    "external_metrics.py",
    "external_policy.py",
    "external_probe.py",
    "journal.py",
    "metrics.py",
    "native.py",
    "portainer.py",
    "probes.py",
    "provenance.py",
    "providers.py",
    "publication.py",
    "release.py",
    "runtime.py",
    "transport.py",
    "validation.py",
)
TOOL_PATHS = frozenset(
    {"deployment/staging/release/" + name for name in TOOL_NAMES}
    | {"backend/pyproject.toml", "backend/uv.lock", "backend/.python-version"}
)
MAX_REQUEST = 16 * 1024
MAX_RESPONSE = 16 * 1024 * 1024
TOKEN_LIMIT = 8192
PAGE_SIZE = 100
REQUEST_SECONDS = 15
SERVICE_SECONDS = 1200
WORK_ROOT = Path("/var/lib/peerly-release-ssh")
INPUT_FILE = Path("/etc/peerly-release-ssh/inputs.json")
ADMISSION_FILE = Path("/etc/peerly-release-ssh/admission.json")
ROOT_FILE_MODE = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP

INPUT_NAMES = frozenset(
    {
        "PEERLY_PORTAINER_ORIGIN",
        "PEERLY_PORTAINER_API_KEY",
        "PEERLY_STAGING_METRICS_ORIGIN",
        "PEERLY_STAGING_METRICS_PASSWORD",
        "PEERLY_SMOKE_SESSION",
        "PEERLY_SMOKE_ACCOUNT_ID",
        "PEERLY_CANONICAL_AI_CONTAINER_ID",
        "PEERLY_STAGING_DATABASE_NAME",
        "PEERLY_RELEASE_STATE_DIR",
    }
)


class AdmissionError(RuntimeError):
    """Fixed safe diagnostic; no remote body or input may enter logs."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise AdmissionError(code)


def pairs_unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        require(key not in result, "duplicate_json_key")
        result[key] = value
    return result


def object_value(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AdmissionError("object_required")
    return {str(key): item for key, item in value.items()}


def document(raw: bytes) -> dict[str, object]:
    value: object = json.loads(raw, object_pairs_hook=pairs_unique)
    return object_value(value)


def string(value: object) -> str:
    if not isinstance(value, str):
        raise AdmissionError("string_required")
    return value


@dataclass(frozen=True, slots=True)
class Request:
    operation: str
    source_sha: str
    run_id: int
    run_attempt: int
    recovery_attempt: str
    reconcile_attempt: str
    compatible_schema: str
    github_token: str

    @property
    def attempt(self) -> str:
        return f"{self.run_id}-{self.run_attempt}"

    @classmethod
    def parse(cls, raw: bytes) -> Request:
        require(len(raw) <= MAX_REQUEST, "request_limit")
        obj = document(raw)
        require(
            set(obj)
            == {
                "protocol",
                "operation",
                "source_sha",
                "run_id",
                "run_attempt",
                "recovery_attempt",
                "reconcile_attempt",
                "compatible_schema",
                "github_token",
            },
            "request_fields",
        )
        require(type(obj["protocol"]) is int and obj["protocol"] == 1, "protocol")
        run_id, attempt = obj["run_id"], obj["run_attempt"]
        require(type(run_id) is int and type(attempt) is int, "run_identity")
        if not isinstance(run_id, int) or not isinstance(attempt, int):
            raise AdmissionError("run_identity")
        require(0 < run_id < 10**20 and 0 < attempt < 10**4, "run_identity")
        result = cls(
            string(obj["operation"]),
            string(obj["source_sha"]),
            run_id,
            attempt,
            string(obj["recovery_attempt"]),
            string(obj["reconcile_attempt"]),
            string(obj["compatible_schema"]),
            string(obj["github_token"]),
        )
        result.validate()
        return result

    def validate(self) -> None:
        require(
            self.operation in {"promote", "rollback", "reconcile"}
            and re.fullmatch(r"[0-9a-f]{40}", self.source_sha) is not None,
            "operation_or_source",
        )
        require(
            0 < len(self.github_token) <= TOKEN_LIMIT
            and all(c.isascii() and (c.isalnum() or c in "._-") for c in self.github_token),
            "token_shape",
        )
        for value in (self.recovery_attempt, self.reconcile_attempt):
            require(
                not value or re.fullmatch(r"[0-9]{1,20}-[0-9]{1,4}", value) is not None,
                "attempt_scope",
            )
        if self.operation == "promote":
            require(
                not any((self.recovery_attempt, self.reconcile_attempt, self.compatible_schema)),
                "promotion_ack_fields",
            )
        else:
            require(
                bool(self.recovery_attempt) and self.compatible_schema == "0060_report_triage",
                "recovery_ack",
            )
            require(
                self.operation != "reconcile" or bool(self.reconcile_attempt), "reconciliation_ack"
            )

    def cli_arguments(self, state: Path) -> tuple[str, ...]:
        recovery = (
            str(state / self.recovery_attempt / "recovery.private.json")
            if self.recovery_attempt
            else ""
        )
        return (
            "--operation",
            self.operation,
            "--sha",
            self.source_sha,
            "--attempt",
            self.attempt,
            "--recovery",
            recovery,
            "--reconcile-attempt",
            self.reconcile_attempt,
            "--compatible-schema",
            self.compatible_schema,
        )


async def read_request() -> bytes:
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader(limit=MAX_REQUEST)
    pipe, _ = await loop.connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(reader), sys.stdin.buffer
    )
    try:
        async with asyncio.timeout(REQUEST_SECONDS):
            raw = await reader.readline()
            require(raw.endswith(b"\n") and len(raw) <= MAX_REQUEST, "request_line")
            require(not await reader.read(1), "request_trailing_bytes")
            return raw
    finally:
        pipe.close()


def root_document(path: Path) -> dict[str, object]:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        meta = os.fstat(fd)
        require(
            stat.S_ISREG(meta.st_mode)
            and meta.st_uid == 0
            and meta.st_gid == os.getgid()
            and stat.S_IMODE(meta.st_mode) == ROOT_FILE_MODE,
            "root_protected_input",
        )
        raw = os.read(fd, MAX_RESPONSE + 1)
        require(len(raw) <= MAX_RESPONSE, "root_input_limit")
        return document(raw)
    finally:
        os.close(fd)


class Github:
    def __init__(self, token: str) -> None:
        self.token = token

    async def get(self, path: str) -> dict[str, object]:
        require(path.startswith(REPO + "/"), "fixed_repository")

        def read() -> bytes:
            connection = http.client.HTTPSConnection("api.github.com", timeout=20)
            try:
                connection.request(
                    "GET",
                    path,
                    headers={
                        "Authorization": "Bearer " + self.token,
                        "Accept": "application/vnd.github+json",
                        "User-Agent": "peerly-staging-ssh",
                    },
                )
                response = connection.getresponse()
                raw = response.read(MAX_RESPONSE + 1)
                require(
                    response.status == http.client.OK and len(raw) <= MAX_RESPONSE,
                    "github_response",
                )
                return raw
            finally:
                connection.close()

        return document(await asyncio.to_thread(read))

    async def main_sha(self) -> str:
        branch = await self.get(REPO + "/branches/main")
        sha = string(object_value(branch["commit"])["sha"])
        require(re.fullmatch(r"[0-9a-f]{40}", sha) is not None, "main_sha")
        return sha

    async def blob(self, sha: str) -> bytes:
        require(re.fullmatch(r"[0-9a-f]{40}", sha) is not None, "blob_identity")
        value = await self.get(REPO + "/git/blobs/" + sha)
        require(value.get("encoding") == "base64", "blob_encoding")
        raw = base64.b64decode(string(value["content"]))
        actual = hashlib.sha1(
            b"blob " + str(len(raw)).encode() + b"\0" + raw, usedforsecurity=False
        ).hexdigest()
        require(actual == sha, "git_blob_hash")
        return raw

    async def admit_run(self, request: Request, tool_sha: str) -> str:
        run = await self.get(REPO + f"/actions/runs/{request.run_id}")
        require(
            run.get("id") == request.run_id
            and run.get("run_attempt") == request.run_attempt
            and run.get("path") == ".github/workflows/staging-release.yml"
            and run.get("head_sha") == tool_sha
            and run.get("head_branch") == "main"
            and run.get("status") == "in_progress"
            and run.get("event") in {"workflow_run", "workflow_dispatch"}
            and object_value(run["repository"]).get("full_name") == "Mark0000dev/Peerly"
            and object_value(run["head_repository"]).get("full_name") == "Mark0000dev/Peerly",
            "deployment_run",
        )
        if request.operation == "promote":
            require(request.source_sha == tool_sha, "selected_main_moved")
        actor = string(object_value(run["actor"])["login"])
        require(re.fullmatch(r"[A-Za-z0-9-]{1,39}", actor) is not None, "github_actor")
        query = f"?head_sha={tool_sha}&branch=main&event=push&per_page=100"
        quality = await self.get(
            REPO + "/actions/workflows/staging-release-quality.yml/runs" + query
        )
        candidates = quality["workflow_runs"]
        if not isinstance(candidates, list):
            raise AdmissionError("quality_runs")
        good = [
            object_value(item)
            for item in candidates
            if object_value(item).get("head_sha") == tool_sha
            and object_value(item).get("head_branch") == "main"
            and object_value(item).get("event") == "push"
            and object_value(item).get("status") == "completed"
            and object_value(item).get("conclusion") == "success"
        ]
        if (
            len(good) == 1
            and good[0].get("path") == ".github/workflows/staging-release-quality.yml"
        ):
            return actor
        jobs = await self.get(
            REPO
            + f"/actions/runs/{request.run_id}/attempts/{request.run_attempt}/jobs?per_page=100"
        )
        require(
            type(jobs.get("total_count")) is int and int(str(jobs["total_count"])) <= PAGE_SIZE,
            "quality_job_pagination",
        )
        values = jobs["jobs"]
        if not isinstance(values, list):
            raise AdmissionError("quality_jobs")
        names = {
            "Release tool quality / Staging release strict offline quality",
            "Staging release strict offline quality",
        }
        checked = [
            object_value(item)
            for item in values
            if object_value(item).get("name") in names
            and object_value(item).get("status") == "completed"
            and object_value(item).get("conclusion") == "success"
            and object_value(item).get("head_sha") == tool_sha
            and object_value(item).get("run_id") == request.run_id
        ]
        require(len(checked) == 1, "main_helper_quality_required")
        return actor

    async def fetch_tool(self, sha: str, destination: Path) -> None:
        tree = await self.get(REPO + "/git/trees/" + sha + "?recursive=1")
        require(
            tree.get("truncated") is False and isinstance(tree.get("tree"), list),
            "complete_main_tree",
        )
        members = tree["tree"]
        if not isinstance(members, list):
            raise AdmissionError("main_tree")
        indexed = {string(object_value(item)["path"]): object_value(item) for item in members}
        # V3 readiness alone cannot certify a native-enabled image against0060.
        # Temporary fail-closed fence for the known NEW migration, not a0061
        # compatibility allowlist. Replace only with the reviewed image/schema/
        # config barrier; this source check is NOT actual baked-image head proof.
        require(
            "backend/migrations/versions/0061_native_login.py" not in indexed,
            "reviewed_native_schema_barrier_required",
        )
        require(MANIFEST in indexed and indexed.keys() >= TOOL_PATHS, "tool_tree_paths")
        require(
            indexed[MANIFEST].get("type") == "blob" and indexed[MANIFEST].get("mode") == "100644",
            "regular_manifest_required",
        )
        manifest = document(await self.blob(string(indexed[MANIFEST]["sha"])))
        require(
            type(manifest.get("format")) is int
            and manifest.get("format") == 1
            and set(object_value(manifest.get("files"))) == TOOL_PATHS,
            "tool_manifest_scope",
        )
        hashes = object_value(manifest["files"])
        for path in sorted(TOOL_PATHS):
            item = indexed[path]
            require(
                item.get("type") == "blob" and item.get("mode") == "100644",
                "regular_main_source_only",
            )
            raw = await self.blob(string(item["sha"]))
            expected = string(hashes[path])
            require(
                re.fullmatch(r"[0-9a-f]{64}", expected) is not None
                and hashlib.sha256(raw).hexdigest() == expected,
                "tool_sha256",
            )
            target = destination / path
            await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
            await asyncio.to_thread(target.write_bytes, raw)
        require(await self.main_sha() == sha, "main_moved_during_fetch")


def admission(value: dict[str, object]) -> None:
    expected: dict[str, object] = {
        "repository": "Mark0000dev/Peerly",
        "environment": "internal-staging",
        "branch": "main",
        "approved_by": "Mark0000dev",
        "environment_main_only_verified": True,
        "host_key_pinned_verified": True,
    }
    require(
        set(value) == set(expected)
        and all(
            type(value[key]) is type(item) and value[key] == item for key, item in expected.items()
        ),
        "mark_admission_not_accepted",
    )


def base_environment() -> dict[str, str]:
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(WORK_ROOT),
        "PYTHONDONTWRITEBYTECODE": "1",
        "UV_NO_PROGRESS": "1",
        "UV_CACHE_DIR": str(WORK_ROOT / "cache"),
        "UV_PYTHON_DOWNLOADS": "never",
    }


def service_arguments(request: Request) -> tuple[str, ...]:
    return (
        "/usr/bin/systemd-run",
        "--user",
        "--quiet",
        "--pipe",
        "--wait",
        "--collect",
        "--unit=peerly-release-" + request.attempt,
        f"--property=RuntimeMaxSec={SERVICE_SECONDS}",
        "--property=TimeoutStopSec=5s",
        "--property=KillMode=control-group",
        "--property=NoNewPrivileges=yes",
        "--property=ProtectSystem=strict",
        "--property=ProtectHome=yes",
        "--property=PrivateUsers=yes",
        "--property=PrivateTmp=yes",
        "--property=PrivateDevices=yes",
        "--property=CapabilityBoundingSet=",
        "--property=RestrictSUIDSGID=yes",
        "--property=ProtectControlGroups=yes",
        "--property=MemoryMax=1G",
        "--property=CPUQuota=50%",
        "--property=LimitCORE=0",
        "--property=StandardOutput=null",
        "--property=StandardError=null",
        (
            "--property=InaccessiblePaths=-/run/docker.sock -/var/run/docker.sock "
            "-/run/containerd/containerd.sock"
        ),
        "--property=ReadWritePaths=/var/lib/peerly-release-ssh /var/lib/peerly-release",
        "/usr/bin/env",
        "-i",
        "PATH=/usr/local/bin:/usr/bin:/bin",
        f"HOME={WORK_ROOT}",
        "/usr/bin/python3",
        "-I",
        "/opt/peerly-release-ssh/broker.py",
        "--worker",
    )


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
        await asyncio.sleep(0.2)
        signal_group(process.pid, signal.SIGKILL)
    async with asyncio.timeout(2.0):
        await process.wait()


async def quiet_command(
    argv: tuple[str, ...], env: dict[str, str], cwd: Path | None, raw: bytes | None = None
) -> int:
    creation = asyncio.create_task(
        asyncio.create_subprocess_exec(
            *argv,
            start_new_session=True,
            env=env,
            cwd=cwd,
            stdin=asyncio.subprocess.PIPE if raw is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    )
    process, interrupted = await finish_shielded(creation)
    cancellation: asyncio.CancelledError | None = None
    try:
        if interrupted:
            raise asyncio.CancelledError
        await process.communicate(raw)
        require(process.returncode is not None, "command_wait")
        if process.returncode is None:
            raise AdmissionError("command_wait")
        return process.returncode
    except asyncio.CancelledError as error:
        cancellation = error
        raise
    finally:
        try:
            _, interrupted = await finish_shielded(asyncio.create_task(cleanup_owned(process)))
        except (OSError, TimeoutError) as error:
            if cancellation is not None:
                raise cancellation from error
            raise
        if interrupted:
            raise asyncio.CancelledError


def host_inputs(value: dict[str, object]) -> dict[str, str]:
    require(set(value) == INPUT_NAMES, "host_input_scope")
    result = {name: string(item) for name, item in value.items()}
    require(
        all(item and "\n" not in item and "\r" not in item for item in result.values()),
        "host_input_value",
    )
    # Deliberately the SAME existing v3 persistent lock/state path.
    require(
        result["PEERLY_RELEASE_STATE_DIR"] == "/var/lib/peerly-release", "shared_stack4_state_path"
    )
    return result


def trusted_executable(path: Path) -> None:
    meta = path.lstat()
    require(
        stat.S_ISREG(meta.st_mode) and meta.st_uid == 0 and not meta.st_mode & 0o022,
        "root_owned_tool_executable",
    )


def private_work_root() -> None:
    meta = WORK_ROOT.lstat()
    require(
        stat.S_ISDIR(meta.st_mode)
        and meta.st_uid == os.getuid()
        and stat.S_IMODE(meta.st_mode) == stat.S_IRWXU,
        "private_work_root",
    )


async def worker(request: Request) -> None:
    import tempfile

    await asyncio.to_thread(private_work_root)
    github = Github(request.github_token)
    tool_sha = await github.main_sha()
    actor = await github.admit_run(request, tool_sha)
    with tempfile.TemporaryDirectory(prefix="tool-", dir=WORK_ROOT / "tmp") as directory:
        root = Path(directory)
        await github.fetch_tool(tool_sha, root)
        # Only trusted, hash-verified main tool/dependency inputs can run, and
        # only AFTER the current-main helper quality run passed.
        env = base_environment()
        await asyncio.to_thread(trusted_executable, Path("/usr/local/bin/uv"))
        async with asyncio.timeout(180):
            code = await quiet_command(
                (
                    "/usr/local/bin/uv",
                    "sync",
                    "--locked",
                    "--python",
                    "3.12",
                    "--project",
                    str(root / "backend"),
                    "--no-install-project",
                ),
                env,
                root,
            )
        require(code == 0, "locked_dependencies_failed")
        require(await github.main_sha() == tool_sha, "main_moved_before_exec")
        # Provider inputs are loaded last, never before main/admission/hash gates.
        inputs = host_inputs(await asyncio.to_thread(root_document, INPUT_FILE))
        env.update(inputs)
        env.update(
            {
                "PEERLY_GITHUB_TOKEN": request.github_token,
                "PEERLY_GHCR_USERNAME": actor,
                "PEERLY_GHCR_TOKEN": request.github_token,
            }
        )
        argv = (
            str(root / "backend/.venv/bin/python"),
            "-m",
            "deployment.staging.release.cli",
            *request.cli_arguments(Path(inputs["PEERLY_RELEASE_STATE_DIR"])),
        )
        try:
            code = await quiet_command(argv, env, root)
        finally:
            env.clear()
        require(code == 0, "release_failed_or_unknown_reconcile")
        receipt_path = Path(inputs["PEERLY_RELEASE_STATE_DIR"]) / request.attempt / "receipt.json"
        receipt = await asyncio.to_thread(receipt_path.read_bytes)
        verified = document(receipt)
        phases = {
            "promote": {"verified", "already_verified"},
            "rollback": {"rollback_verified"},
            "reconcile": {"reconcile_verified"},
        }
        require(
            verified.get("sha") == request.source_sha
            and verified.get("operation") == request.operation
            and verified.get("phase") in phases[request.operation],
            "verified_v3_receipt_required",
        )


async def serve(is_worker: bool) -> None:
    require(os.getuid() != 0 and not sys.stdin.isatty(), "nonroot_pipe_required")
    if not is_worker:
        require(
            os.environ.get("SSH_ORIGINAL_COMMAND") == COMMAND and not os.environ.get("SSH_TTY"),
            "forced_command_only",
        )
    raw = await read_request()
    request = Request.parse(raw)
    admission(await asyncio.to_thread(root_document, ADMISSION_FILE))
    if is_worker:
        await worker(request)
    else:
        # No provider secrets or caller-controlled environment is passed into the
        # transient unit. Only the bounded request reaches it through stdin.
        env = base_environment()
        env.update(
            {
                "XDG_RUNTIME_DIR": f"/run/user/{os.getuid()}",
                "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{os.getuid()}/bus",
            }
        )
        async with asyncio.timeout(SERVICE_SECONDS + 30):
            code = await quiet_command(service_arguments(request), env, None, raw)
        require(code == 0, "remote_failed_or_unknown_reconcile")
        sys.stdout.write(
            json.dumps({"protocol": 1, "outcome": "verified", "attempt": request.attempt}) + "\n"
        )


def main() -> int:
    require(sys.argv[1:] in ([], ["--worker"]), "closed_broker_arguments")
    # A dropped client does NOT imply cancellation or retry. The transient unit
    # continues to a bounded result; its RuntimeMaxSec/KillMode bound the full tree.
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    try:
        asyncio.run(serve(sys.argv[1:] == ["--worker"]))
    except (OSError, ValueError, RuntimeError, KeyError, TimeoutError, http.client.HTTPException):
        sys.stderr.write("staging_ssh_failed_or_unknown_no_retry\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
