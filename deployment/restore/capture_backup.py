"""Parent-run bounded source capture; no credentials in argv, stderr or receipts."""

import argparse
import asyncio
import contextlib
import ipaddress
import json
import os
import re
import signal
import stat
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from deployment.restore.accept_restore import MAX_DUMP_BYTES, MAX_JSON, digest, inventory, unique
from deployment.restore.recovery_checks import catalog

SQL_SHA256 = "f4be591e5a15edde65eba095a09c4161925be5babe554a6b02539de3cbf38a64"
CATALOG_SQL_SHA256 = "621fa7039207b1657f78948098afa9c9c279c066d02ff08d36d1d3f43ee710dc"
PG_MAJOR = 16
MAX_PORT = 65535
PRIVATE_FILE_MODE = 0o600
MAX_PRIVATE_FILE = 65536
METADATA_LIMIT = 16384
REQUEST_LIMIT = 16384
CAPTURE_SECONDS = 180
CLOSE_SECONDS = 3
SNAPSHOT = re.compile(r"[0-9A-F]+-[0-9A-F]+-[0-9]+")
HEAD = re.compile(r"[0-9]{4}_[a-z0-9_]{1,80}")
VERSION = re.compile(rb"(?:psql|pg_dump) \(PostgreSQL\) ([0-9]+)[.][^\r\n]{1,120}\n?")
IDENTITY_SQL = """BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT json_build_object(
 'database',current_database(),
 'database_oid',(SELECT oid::text FROM pg_database WHERE datname=current_database()),
 'capabilities',json_build_object(
  'connect',has_database_privilege(current_user,current_database(),'CONNECT'),
  'unreadable_tables',(SELECT count(*) FROM pg_class c
    JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p')
    AND NOT has_table_privilege(c.oid,'SELECT')),
  'unreadable_sequences',(SELECT count(*) FROM pg_class c
    JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='S'
    AND CASE WHEN c.relkind='S' THEN NOT has_sequence_privilege(c.oid,'SELECT')
             ELSE false END),
  'rls_tables',(SELECT count(*) FROM pg_class c
    JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relrowsecurity),
  'superuser',(SELECT rolsuper FROM pg_roles WHERE rolname=current_user),
  'bypass_rls',(SELECT rolbypassrls FROM pg_roles WHERE rolname=current_user),
  'control_system',has_function_privilege(current_user,'pg_catalog.pg_control_system()','EXECUTE')),
 'server_version_num',current_setting('server_version_num')::integer,
 'server_address',coalesce(inet_server_addr()::text,'unix'),
 'server_port',current_setting('port')::integer,
 'role',current_user,
 'read_only',current_setting('transaction_read_only'),
 'heads',(SELECT json_agg(version_num ORDER BY version_num) FROM public.alembic_version),
 'snapshot',pg_export_snapshot());
"""
TABLE_SQL = """SELECT format($fingerprint$
 SELECT jsonb_build_object('table', %L, 'rows', count(*), 'sha256',
 encode(sha256(convert_to(coalesce(string_agg(d, '' ORDER BY d COLLATE "C"), ''),
 'UTF8')), 'hex')) FROM
 (SELECT encode(sha256(convert_to(to_jsonb(t)::text, 'UTF8')), 'hex') d
 FROM (SELECT * FROM public.%I LIMIT 10001) t) bounded
$fingerprint$, tablename, tablename)
FROM pg_tables WHERE schemaname='public' ORDER BY tablename LIMIT 257
\\gexec
"""


class CaptureError(ValueError):
    """Closed technical rejection with no raw input attached."""


def exact_server_address(value: str) -> str:
    interface = ipaddress.ip_interface(value)
    if interface.network.prefixlen != interface.max_prefixlen:
        raise CaptureError("exact_server_address_required")
    return str(interface.ip)


@dataclass(frozen=True, slots=True)
class Request:
    destination: Path
    psql: Path
    pg_dump: Path
    host: str = field(repr=False)
    port: int
    database: str
    role: str
    system_identifier: str | None
    endpoint_address: str
    server_address: str
    server_port: int
    plaintext_approval: str | None
    database_oid: str
    major: int
    head: str
    sslmode: str

    def __post_init__(self) -> None:
        if not all(path.is_absolute() for path in (self.destination, self.psql, self.pg_dump)):
            raise CaptureError("absolute_paths")
        if not self.host or any(ch in self.host for ch in ("\x00", "\n", "\r", "=", " ")):
            raise CaptureError("endpoint")
        for name in (self.database, self.role):
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", name):
                raise CaptureError("identity")
        if (
            not 1 <= self.port <= MAX_PORT
            or (self.system_identifier is not None and not self.system_identifier.isdecimal())
            or not 1 <= self.server_port <= MAX_PORT
            or not self.database_oid.isdecimal()
            or self.major != PG_MAJOR
            or HEAD.fullmatch(self.head) is None
            or self.sslmode not in {"verify-full", "disable"}
        ):
            raise CaptureError("expected_identity")
        ipaddress.ip_address(self.endpoint_address)
        exact_server_address(self.server_address)
        if self.sslmode == "disable" and (
            self.plaintext_approval is None
            or re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", self.plaintext_approval) is None
        ):
            raise CaptureError("explicit_plaintext_approval_required")


def read_request(descriptor: int) -> Request:
    private_fd(descriptor)
    with os.fdopen(os.dup(descriptor), "rb") as stream:
        raw = stream.read(REQUEST_LIMIT + 1)
    if len(raw) > REQUEST_LIMIT:
        raise CaptureError("request_bound")
    value: object = json.loads(raw, object_pairs_hook=unique)
    names = set(Request.__dataclass_fields__)
    if not isinstance(value, dict) or set(value) != names:
        raise CaptureError("request_shape")
    for name in names - {"port", "major", "server_port", "system_identifier", "plaintext_approval"}:
        if not isinstance(value[name], str):
            raise CaptureError("request_shape")
    for name in ("system_identifier", "plaintext_approval"):
        if value[name] is not None and not isinstance(value[name], str):
            raise CaptureError("request_shape")
    if any(type(value[name]) is not int for name in ("port", "major", "server_port")):
        raise CaptureError("request_shape")
    return Request(
        destination=Path(value["destination"]),
        psql=Path(value["psql"]),
        pg_dump=Path(value["pg_dump"]),
        host=value["host"],
        port=value["port"],
        database=value["database"],
        role=value["role"],
        system_identifier=value["system_identifier"],
        endpoint_address=value["endpoint_address"],
        server_address=value["server_address"],
        server_port=value["server_port"],
        plaintext_approval=value["plaintext_approval"],
        database_oid=value["database_oid"],
        major=value["major"],
        head=value["head"],
        sslmode=value["sslmode"],
    )


def private_fd(descriptor: int) -> None:
    info = os.fstat(descriptor)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != PRIVATE_FILE_MODE
        or not 0 < info.st_size <= MAX_PRIVATE_FILE
    ):
        raise CaptureError("private_descriptor")


def connection_env(request: Request, password_fd: int, ca_fd: int | None) -> dict[str, str]:
    private_fd(password_fd)
    if ca_fd is not None:
        private_fd(ca_fd)
    if request.sslmode == "verify-full" and ca_fd is None:
        raise CaptureError("explicit_ca_required")
    result = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/nonexistent",
        "LANG": "C",
        "LC_ALL": "C",
        "PGHOST": request.host,
        "PGHOSTADDR": request.endpoint_address,
        "PGPORT": str(request.port),
        "PGDATABASE": request.database,
        "PGUSER": request.role,
        "PGPASSFILE": f"/proc/self/fd/{password_fd}",
        "PGSSLMODE": request.sslmode,
        "PGCONNECT_TIMEOUT": "5",
        "PGOPTIONS": "-c default_transaction_read_only=on -c search_path=pg_catalog,public "
        "-c statement_timeout=120000 "
        "-c lock_timeout=2000 -c idle_in_transaction_session_timeout=200000",
        "PGAPPNAME": "peerly-backup-capture",
        "PGGSSENCMODE": "disable",
        "PGSERVICEFILE": "/nonexistent/pg_service.conf",
        "PGSSLCERT": "/nonexistent/client.crt",
        "PGSSLKEY": "/nonexistent/client.key",
    }
    if ca_fd is not None:
        result["PGSSLROOTCERT"] = f"/proc/self/fd/{ca_fd}"
    return result


def readonly_sql(path: Path, snapshot: str) -> bytes:
    if digest(path, MAX_JSON) != SQL_SHA256 or SNAPSHOT.fullmatch(snapshot) is None:
        raise CaptureError("sql_or_snapshot_pin")
    original = path.read_text()
    tail = original[original.index("WITH retained AS (") :]
    tail = tail.replace("'tables', pg_temp.peerly_inventory()", "'tables', '{}'::jsonb")
    prefix = (
        "\\set ON_ERROR_STOP on\nSET statement_timeout='120s'; SET lock_timeout='2s';\n"
        "SET timezone='UTC'; SET extra_float_digits=3;\n"
        "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\n"
        f"SET TRANSACTION SNAPSHOT '{snapshot}';\n"
    )
    return (prefix + TABLE_SQL + tail).encode()


def baseline(raw: bytes, head: str) -> bytes:
    tables: dict[str, object] = {}
    final: dict[str, object] | None = None
    for line in raw.splitlines():
        value: object = json.loads(line, object_pairs_hook=unique)
        if not isinstance(value, dict):
            raise CaptureError("baseline_shape")
        if set(value) == {"table", "rows", "sha256"}:
            name: object = value["table"]
            if not isinstance(name, str) or name in tables or final is not None:
                raise CaptureError("baseline_tables")
            tables[name] = {"rows": value["rows"], "sha256": value["sha256"]}
        elif final is None and value.get("tables") == {}:
            final = {key: item for key, item in value.items() if isinstance(key, str)}
        else:
            raise CaptureError("baseline_shape")
    if final is None or final["heads"] != [head]:
        raise CaptureError("baseline_head")
    final["tables"] = tables
    inventory(final)
    return (json.dumps(final, sort_keys=True, separators=(",", ":")) + "\n").encode()


def identity(raw: bytes, request: Request, *, enforce: bool = True) -> dict[str, object]:
    value: object = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise CaptureError("source_identity")
    raw_address: object = value.get("server_address")
    if not isinstance(raw_address, str):
        raise CaptureError("source_identity")
    value["server_address"] = exact_server_address(raw_address)
    expected: dict[str, object] = {
        "database": request.database,
        "database_oid": request.database_oid,
        "role": request.role,
        "server_port": request.server_port,
        "server_address": exact_server_address(request.server_address),
        "read_only": "on",
        "heads": [request.head],
    }
    mismatches = [
        key
        for key, item in expected.items()
        if type(value.get(key)) is not type(item) or value.get(key) != item
    ]
    version: object = value.get("server_version_num")
    snapshot: object = value.get("snapshot")
    if type(version) is not int or version // 10000 != request.major:
        mismatches.append("server_version_num")
    if not isinstance(snapshot, str) or SNAPSHOT.fullmatch(snapshot) is None:
        raise CaptureError("source_identity")
    capabilities: object = value.get("capabilities")
    if not isinstance(capabilities, dict) or set(capabilities) != {
        "connect",
        "unreadable_tables",
        "unreadable_sequences",
        "rls_tables",
        "superuser",
        "bypass_rls",
        "control_system",
    }:
        raise CaptureError("capability_shape")
    for name in ("connect", "superuser", "bypass_rls", "control_system"):
        if type(capabilities[name]) is not bool:
            raise CaptureError("capability_shape")
    for name in ("unreadable_tables", "unreadable_sequences", "rls_tables"):
        count: object = capabilities[name]
        if type(count) is not int or count < 0:
            raise CaptureError("capability_shape")
    if enforce and mismatches:
        raise CaptureError("source_identity")
    return {
        **{key: value.get(key) for key in expected},
        "server_version_num": version,
        "server_address_raw": raw_address,
        "snapshot": snapshot,
        "identity_mismatches": mismatches,
        "capabilities": capabilities,
        "approved_endpoint": {
            "host": request.host,
            "address": request.endpoint_address,
            "port": request.port,
            "sslmode": request.sslmode,
            "plaintext_approval": request.plaintext_approval,
        },
        "system_identifier": None,
        "cluster_identifier_verified": False,
        "identity_limitations": ["cluster_identifier_unavailable"],
    }


async def cluster_identity(
    exporter: asyncio.subprocess.Process,
    source: dict[str, object],
    request: Request,
) -> None:
    caps = source["capabilities"]
    if not isinstance(caps, dict):
        raise CaptureError("capability_shape")
    if request.system_identifier is None:
        source["identity_limitations"] = [
            "cluster_identifier_not_requested"
            if caps["control_system"]
            else "cluster_identifier_unavailable"
        ]
        return
    if caps["control_system"] is True:
        if exporter.stdin is None or exporter.stdout is None:
            raise CaptureError("missing_exporter_pipe")
        exporter.stdin.write(
            b"SELECT system_identifier::text FROM pg_catalog.pg_control_system();\n"
        )
        await exporter.stdin.drain()
        actual = (await exporter.stdout.readline()).decode().strip()
        if re.fullmatch(r"[0-9]{1,24}", actual) is None:
            raise CaptureError("cluster_identity")
        source["system_identifier"] = actual
        source["cluster_identifier_verified"] = request.system_identifier == actual
        source["identity_limitations"] = (
            []
            if request.system_identifier == actual
            else ["cluster_identifier_observed_not_pinned"]
        )
        if request.system_identifier != actual:
            raise CaptureError("cluster_identity")
    else:
        raise CaptureError("required_cluster_identifier_unavailable")


def require_read_capabilities(source: dict[str, object]) -> None:
    caps = source["capabilities"]
    if not isinstance(caps, dict) or (
        caps["connect"] is not True
        or caps["unreadable_tables"] != 0
        or caps["unreadable_sequences"] != 0
    ):
        raise CaptureError("source_read_capabilities")


def exclusive(path: Path) -> int:
    return os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)


def save(path: Path, value: bytes) -> None:
    with os.fdopen(exclusive(path), "wb") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


async def spawn(
    binary: Path,
    args: tuple[str, ...],
    environment: dict[str, str],
    descriptors: tuple[int, ...],
) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        str(binary),
        *args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env=environment,
        pass_fds=descriptors,
        start_new_session=True,
    )


async def stop(process: asyncio.subprocess.Process) -> None:
    if process.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGTERM)
        try:
            await asyncio.wait_for(process.wait(), CLOSE_SECONDS)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            await asyncio.wait_for(process.wait(), CLOSE_SECONDS)


async def feed(process: asyncio.subprocess.Process, data: bytes) -> None:
    if process.stdin is None:
        raise CaptureError("missing_stdin")
    process.stdin.write(data)
    await process.stdin.drain()
    process.stdin.close()


async def collect(process: asyncio.subprocess.Process, limit: int) -> bytes:
    if process.stdout is None:
        raise CaptureError("missing_stdout")
    result = bytearray()
    while chunk := await process.stdout.read(min(65536, limit + 1 - len(result))):
        result.extend(chunk)
        if len(result) > limit:
            raise CaptureError("native_output_bound")
    if await process.wait() != 0:
        raise CaptureError("native_exit")
    return bytes(result)


async def archive(process: asyncio.subprocess.Process, path: Path) -> None:
    if process.stdout is None:
        raise CaptureError("missing_stdout")
    total = 0
    with os.fdopen(exclusive(path), "wb") as stream:
        while chunk := await process.stdout.read(min(65536, MAX_DUMP_BYTES + 1 - total)):
            total += len(chunk)
            if total > MAX_DUMP_BYTES:
                raise CaptureError("archive_bound")
            stream.write(chunk)
        stream.flush()
        os.fsync(stream.fileno())
    if await process.wait() != 0 or total == 0:
        raise CaptureError("archive_exit")
    with path.open("rb") as stream:
        if stream.read(5) != b"PGDMP":
            raise CaptureError("archive_format")


def binary_hash(path: Path) -> str:
    if path.is_symlink():
        raise CaptureError("native_binary")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise CaptureError("native_binary")
    return digest(path, 128 * 1024 * 1024)


async def client(
    path: Path,
    request: Request,
    environment: dict[str, str],
    descriptors: tuple[int, ...],
) -> dict[str, object]:
    hashed = await asyncio.to_thread(binary_hash, path)
    process = await spawn(path, ("--version",), environment, descriptors)
    try:
        await feed(process, b"")
        raw = await collect(process, METADATA_LIMIT)
    finally:
        await stop(process)
    match = VERSION.fullmatch(raw)
    if match is None or int(match[1]) != request.major:
        raise CaptureError("client_major")
    return {"version": raw.decode().strip(), "sha256": hashed}


def publish(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    completion_linked = False
    try:
        for name in ("source.dump", "baseline.json", "source-catalog.json"):
            os.link(directory / (name + ".part"), directory / name, follow_symlinks=False)
            (directory / (name + ".part")).unlink()
        os.fsync(descriptor)
        os.link(
            directory / "complete.json.part", directory / "complete.json", follow_symlinks=False
        )
        completion_linked = True
        (directory / "complete.json.part").unlink()
        os.fsync(descriptor)
    except OSError:
        if completion_linked:
            (directory / "complete.json").unlink(missing_ok=True)
        raise
    finally:
        os.close(descriptor)


def prepare_directory(directory: Path) -> None:
    parent = directory.parent.lstat()
    if (
        not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid != os.geteuid()
        or stat.S_IMODE(parent.st_mode) & 0o077
        or ".." in directory.parts
    ):
        raise CaptureError("private_parent")
    directory.mkdir(mode=0o700, parents=False, exist_ok=False)


async def export_source(
    request: Request,
    environment: dict[str, str],
    descriptors: tuple[int, ...],
    processes: list[asyncio.subprocess.Process],
    *,
    enforce: bool = True,
) -> tuple[asyncio.subprocess.Process, dict[str, object]]:
    exporter = await spawn(
        request.psql,
        ("--no-password", "-X", "-Atq", "--set=ON_ERROR_STOP=1"),
        environment,
        descriptors,
    )
    processes.append(exporter)
    if exporter.stdin is None or exporter.stdout is None:
        raise CaptureError("missing_exporter_pipe")
    exporter.stdin.write(IDENTITY_SQL.encode())
    await exporter.stdin.drain()
    raw = await exporter.stdout.readline()
    if not 0 < len(raw) <= METADATA_LIMIT:
        raise CaptureError("source_metadata_bound")
    source = identity(raw, request, enforce=enforce)
    await cluster_identity(exporter, source, request)
    return exporter, source


async def capture_children(  # noqa: PLR0913 - explicit per-attempt resources and ownership.
    request: Request,
    environment: dict[str, str],
    descriptors: tuple[int, ...],
    source: dict[str, object],
    processes: list[asyncio.subprocess.Process],
    *,
    tasks: list[asyncio.Task[None] | asyncio.Task[bytes]],
) -> None:
    snapshot = source["snapshot"]
    if not isinstance(snapshot, str):
        raise CaptureError("snapshot")
    sql = await asyncio.to_thread(
        readonly_sql, Path(__file__).with_name("acceptance.sql"), snapshot
    )
    catalog_query = await asyncio.to_thread(
        catalog_sql, Path(__file__).with_name("recovery_catalog.sql"), snapshot
    )
    dumper = await spawn(
        request.pg_dump,
        ("--no-password", "--format=custom", "--snapshot=" + snapshot),
        environment,
        descriptors,
    )
    processes.append(dumper)
    await feed(dumper, b"")
    reader = await spawn(
        request.psql,
        ("--no-password", "-X", "-Atq", "--set=ON_ERROR_STOP=1"),
        environment,
        descriptors,
    )
    processes.append(reader)
    await feed(reader, sql)
    catalog_reader = await spawn(
        request.psql,
        ("--no-password", "-X", "-Atq", "--set=ON_ERROR_STOP=1"),
        environment,
        descriptors,
    )
    processes.append(catalog_reader)
    await feed(catalog_reader, catalog_query)
    dump_task = asyncio.create_task(archive(dumper, request.destination / "source.dump.part"))
    baseline_task = asyncio.create_task(collect(reader, MAX_JSON))
    catalog_task = asyncio.create_task(collect(catalog_reader, MAX_JSON))
    tasks.extend((dump_task, baseline_task, catalog_task))
    # Retain one exported snapshot until ALL THREE native consumers exit zero.
    _nothing, captured, captured_catalog = await asyncio.gather(
        dump_task, baseline_task, catalog_task
    )
    encoded = baseline(captured, request.head)
    await asyncio.to_thread(save, request.destination / "baseline.json.part", encoded)
    encoded_catalog = catalog_bytes(captured_catalog, request)
    await asyncio.to_thread(save, request.destination / "source-catalog.json.part", encoded_catalog)


def catalog_sql(path: Path, snapshot: str) -> bytes:
    if SNAPSHOT.fullmatch(snapshot) is None or digest(path, MAX_JSON) != CATALOG_SQL_SHA256:
        raise CaptureError("catalog_sql_or_snapshot_pin")
    text = path.read_text()
    marker = "\\if :{?backup_snapshot}\nSET TRANSACTION SNAPSHOT :'backup_snapshot';\n\\endif"
    if text.count(marker) != 1:
        raise CaptureError("catalog_snapshot_seam")
    return text.replace(marker, "SET TRANSACTION SNAPSHOT '" + snapshot + "';").encode()


def catalog_bytes(raw: bytes, request: Request) -> bytes:
    value: object = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(value, dict) or value.get("database") != request.database:
        raise CaptureError("catalog_source_identity")
    normalized = catalog(value, [request.head])
    value["entries"] = [
        {"kind": kind, "schema": schema, "name": name, "sha256": hashed}
        for (kind, schema, name), hashed in sorted(normalized.items())
    ]
    return (json.dumps(value, sort_keys=True) + "\n").encode()


def receipt_bytes(
    request: Request,
    source: dict[str, object],
    clients: dict[str, dict[str, object]],
    started: str,
) -> bytes:
    receipt = {
        "format": 1,
        "status": "database_capture_complete",
        "database_capture_complete": True,
        "backup_complete": False,
        "capture_id": uuid4().hex,
        "started_at": started,
        "finished_at": datetime.now(UTC).isoformat(),
        "source": source,
        "clients": clients,
        "acceptance_sql_sha256": SQL_SHA256,
        "source_dump_sha256": digest(request.destination / "source.dump.part", MAX_DUMP_BYTES),
        "baseline_sha256": digest(request.destination / "baseline.json.part", MAX_JSON),
        "source_catalog_sha256": digest(request.destination / "source-catalog.json.part", MAX_JSON),
        "source_catalog_sql_sha256": CATALOG_SQL_SHA256,
        "source_catalog_snapshot": source["snapshot"],
        "media_capture_complete": False,
        "full_restore_proven": False,
    }
    return (json.dumps(receipt, sort_keys=True) + "\n").encode()


def failed(directory: Path) -> None:
    for name in (
        "source.dump.part",
        "baseline.json.part",
        "source-catalog.json.part",
        "complete.json.part",
    ):
        (directory / name).unlink(missing_ok=True)
    if not (directory / "complete.json").exists():
        save(directory / "failed.json", b'{"status":"failed","backup_complete":false}\n')


async def close_attempt(
    processes: list[asyncio.subprocess.Process],
    tasks: list[asyncio.Task[None] | asyncio.Task[bytes]],
    directory: Path,
    completed: bool,
) -> None:
    for task in tasks:
        if not task.done():
            task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    closed = await asyncio.gather(
        *(stop(process) for process in reversed(processes)), return_exceptions=True
    )
    if not completed:
        await asyncio.to_thread(failed, directory)
    if any(isinstance(result, BaseException) for result in closed):
        raise CaptureError("native_shutdown")


async def capture(
    request: Request,
    password_fd: int,
    ca_fd: int | None = None,
    *,
    preflight: bool = False,
) -> None:
    environment = connection_env(request, password_fd, ca_fd)
    descriptors = (password_fd,) if ca_fd is None else (password_fd, ca_fd)
    await asyncio.to_thread(prepare_directory, request.destination)
    processes: list[asyncio.subprocess.Process] = []
    tasks: list[asyncio.Task[None] | asyncio.Task[bytes]] = []
    completed = False
    started = datetime.now(UTC).isoformat()
    try:
        async with asyncio.timeout(CAPTURE_SECONDS):
            clients = {
                "psql": await client(request.psql, request, environment, descriptors),
                "pg_dump": await client(request.pg_dump, request, environment, descriptors),
            }
            exporter, source = await export_source(
                request, environment, descriptors, processes, enforce=not preflight
            )
            if preflight:
                await feed(exporter, b"ROLLBACK;\n\\q\n")
                await collect(exporter, METADATA_LIMIT)
                report = {
                    "status": "source_preflight",
                    "source": source,
                    "clients": clients,
                    "backup_complete": False,
                }
                await asyncio.to_thread(
                    save,
                    request.destination / "preflight.json",
                    (json.dumps(report) + "\n").encode(),
                )
                completed = True
                return
            require_read_capabilities(source)
            await capture_children(
                request, environment, descriptors, source, processes, tasks=tasks
            )
            if exporter.returncode is not None:
                raise CaptureError("exporter_lost")
            await feed(exporter, b"ROLLBACK;\n\\q\n")
            if await collect(exporter, METADATA_LIMIT) != b"":
                raise CaptureError("exporter_exit")
            receipt = await asyncio.to_thread(receipt_bytes, request, source, clients, started)
            await asyncio.to_thread(save, request.destination / "complete.json.part", receipt)
        # Publish only after the timeout scope has exited successfully. No await
        # separates the final completion link from the in-process completion flag.
        publish(request.destination)
        completed = True
    finally:
        await close_attempt(processes, tasks, request.destination, completed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request-fd", required=True, type=int)
    parser.add_argument("--password-fd", required=True, type=int)
    parser.add_argument("--ca-fd", type=int)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        request = read_request(args.request_fd)

        async def run() -> None:
            task = asyncio.current_task()
            if task is None:
                raise CaptureError("task")
            asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, task.cancel)
            await capture(request, args.password_fd, args.ca_fd, preflight=args.preflight)

        asyncio.run(run())
    except (OSError, ValueError, TimeoutError, asyncio.CancelledError, KeyboardInterrupt):
        sys.stderr.write("backup_capture_failed\n")
        return 1
    status = "source_preflight" if args.preflight else "database_capture_complete"
    sys.stdout.write(json.dumps({"status": status, "media_capture_complete": False}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
