"""Synthetic native boundary stand-ins; never connect PostgreSQL or real credentials."""

import asyncio
import json
import os
import stat
import sys
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from deployment.restore import capture_backup as capture
from deployment.restore.accept_restore import REQUIRED, load

PRIVATE = "SYNTHETIC_PRIVATE_PASSWORD_MUST_NOT_ESCAPE"
SNAPSHOT = "00000001-00000001-1"
RENDITIONS = 2
EXPORTER_CALL = 3
PRIVATE_DIRECTORY_MODE = 0o700
FAKE_NATIVE = r"""
import json, os, pathlib, sys, time
root=pathlib.Path(os.environ['SYNTHETIC_ROOT'])
mode=sys.argv[1]
config=json.loads((root/'native.json').read_text())
def event(value):
    with (root/'events').open('a') as file:file.write(value+'\n')
if mode=='version':
    print(sys.argv[2]+' (PostgreSQL) '+config.get('client_version','16.15'))
    sys.exit(0)
assert pathlib.Path(os.environ['PGPASSFILE']).read_text() == (
    'SYNTHETIC_PRIVATE_PASSWORD_MUST_NOT_ESCAPE')
if mode=='exporter':
    text=''
    while 'pg_export_snapshot' not in text:
        line=sys.stdin.readline()
        if not line:sys.exit(9)
        text+=line
    event('exported')
    print(json.dumps(config['identity']),flush=True)
    if config.get('early_exporter_exit'):sys.exit(0)
    tail=''
    for line in sys.stdin:
        tail+=line
        if 'SELECT system_identifier::text' in line:
            print(config.get('cluster_identifier','12345'),flush=True)
    assert 'ROLLBACK;' in tail
    event('released')
    sys.exit(0)
text=sys.stdin.read()
event(mode+'_started')
print('SYNTHETIC_PRIVATE_PASSWORD_MUST_NOT_ESCAPE',file=sys.stderr,flush=True)
if config.get('hang')==mode:
    time.sleep(30)
if config.get('slow')==mode:time.sleep(0.12)
if config.get('failure')==mode:sys.exit(12)
if mode=='dump':
    sys.stdout.buffer.write(b'PGDMPsynthetic_archive_not_a_real_backup')
else:
    assert 'READ ONLY' in text and 'CREATE FUNCTION' not in text
    assert "SET TRANSACTION SNAPSHOT '00000001-00000001-1';" in text
    for name, measured in config['baseline']['tables'].items():
        print(json.dumps({'table':name,**measured}))
    final={**config['baseline'],'tables':{}}
    if config.get('wrong_head'):final['heads']=['0001_wrong']
    print(json.dumps(final))
event(mode+'_finished')
"""


def fixture_data() -> dict[str, object]:
    stem = "retained/11111111-1111-1111-1111-111111111111/22222222-2222-2222-2222-222222222222/"
    return {
        "format": 1,
        "heads": ["0060_report_triage"],
        "tables": {name: {"rows": 1, "sha256": "a" * 64} for name in REQUIRED},
        "broken_relationships": 0,
        "unvalidated_constraints": 0,
        "disabled_triggers": 0,
        "objects": [
            {"key": stem + name, "size": 3, "sha256": "b" * 64}
            for name in ("original", "photo.jpg")
        ],
    }


def request(root: Path) -> capture.Request:
    return capture.Request(
        destination=root / "capture",
        psql=Path(sys.executable).resolve(),
        pg_dump=Path(sys.executable).resolve(),
        host="127.0.0.1",
        port=55433,
        database="synthetic_source",
        role="synthetic_reader",
        system_identifier=None,
        endpoint_address="127.0.0.1",
        server_address="10.20.30.40",
        server_port=5432,
        plaintext_approval="synthetic-parent-explicit-approval",
        database_oid="16384",
        major=16,
        head="0060_report_triage",
        sslmode="disable",
    )


def metadata(req: capture.Request) -> dict[str, object]:
    return {
        "database": req.database,
        "database_oid": req.database_oid,
        "capabilities": {
            "connect": True,
            "unreadable_tables": 0,
            "unreadable_sequences": 0,
            "rls_tables": 0,
            "superuser": False,
            "bypass_rls": False,
            "control_system": False,
        },
        "server_version_num": 160015,
        "server_address": req.server_address,
        "server_port": req.server_port,
        "role": req.role,
        "read_only": "on",
        "heads": [req.head],
        "snapshot": SNAPSHOT,
    }


class StandIn:
    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.root = root
        self.binary = Path(sys.executable).resolve()
        self.request = request(root)
        self.config: dict[str, object] = {
            "identity": metadata(self.request),
            "baseline": fixture_data(),
        }
        self.environments: list[dict[str, str]] = []
        self.processes: list[asyncio.subprocess.Process] = []
        self.baseline_spawned = asyncio.Event()
        self.script = root / "native.py"
        self.script.write_text(FAKE_NATIVE)
        password = root / "synthetic.pgpass"
        password.write_text(PRIVATE)
        password.chmod(0o600)
        self.descriptor = os.open(password, os.O_RDONLY)
        monkeypatch.setattr(capture, "spawn", self.spawn)

    async def spawn(
        self,
        binary: Path,
        args: tuple[str, ...],
        environment: dict[str, str],
        descriptors: tuple[int, ...],
    ) -> asyncio.subprocess.Process:
        self.environments.append(environment.copy())
        extra: tuple[str, ...]
        if args == ("--version",):
            mode = "version"
            kind = "psql" if len(self.environments) == 1 else "pg_dump"
            extra = (kind,)
        elif "--format=custom" in args:
            mode, extra = "dump", ()
        elif len(self.environments) == EXPORTER_CALL:
            mode, extra = "exporter", ()
        else:
            mode, extra = "baseline", ()
        assert binary == self.binary
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-B",
            str(self.script),
            mode,
            *extra,
            env={**environment, "SYNTHETIC_ROOT": str(self.root)},
            pass_fds=descriptors,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
        self.processes.append(process)
        if mode == "baseline":
            self.baseline_spawned.set()
        return process

    async def run(self) -> None:
        (self.root / "native.json").write_text(json.dumps(self.config))
        try:
            await capture.capture(self.request, self.descriptor)
        finally:
            os.close(self.descriptor)
        assert all(process.returncode is not None for process in self.processes)


@pytest.mark.parametrize("slow", ["dump", "baseline"])
async def test_both_children_finish_before_snapshot_release_and_private_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    slow: str,
) -> None:
    scenario = StandIn(tmp_path, monkeypatch)
    scenario.config["slow"] = slow
    monkeypatch.setenv("HOME", "/developer-private")
    monkeypatch.setenv("PGSERVICE", PRIVATE)
    monkeypatch.setenv("PGPASSWORD", PRIVATE)
    await scenario.run()
    events = (tmp_path / "events").read_text().splitlines()
    assert events.index("released") > events.index("dump_finished")
    assert events.index("released") > events.index("baseline_finished")
    output = scenario.request.destination
    receipt = load(output / "complete.json")
    assert receipt["database_capture_complete"] is True
    assert receipt["backup_complete"] is False
    assert receipt["media_capture_complete"] is False
    assert receipt["full_restore_proven"] is False
    assert load(output / "baseline.json") == fixture_data()
    for name in ("source.dump", "baseline.json", "complete.json"):
        assert stat.S_IMODE((output / name).stat().st_mode) == capture.PRIVATE_FILE_MODE
    assert stat.S_IMODE(output.stat().st_mode) == PRIVATE_DIRECTORY_MODE
    for env in scenario.environments:
        assert env["HOME"] == "/nonexistent"
        assert "PGPASSWORD" not in env
        assert "PGSERVICE" not in env
        assert env["PGOPTIONS"].startswith("-c default_transaction_read_only=on")
    assert PRIVATE not in (output / "complete.json").read_text()
    assert PRIVATE not in capsys.readouterr().err
    assert list(output.glob("*.part")) == []


@pytest.mark.parametrize("failure", ["dump", "baseline"])
async def test_partial_native_failure_reaps_peers_and_never_publishes_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    scenario = StandIn(tmp_path, monkeypatch)
    scenario.config["failure"] = failure
    scenario.config["hang"] = "baseline" if failure == "dump" else "dump"
    with pytest.raises(capture.CaptureError, match=r"native_exit|archive_exit"):
        await scenario.run()
    assert all(process.returncode is not None for process in scenario.processes)
    assert not (scenario.request.destination / "complete.json").exists()
    assert list(scenario.request.destination.glob("*.part")) == []
    assert load(scenario.request.destination / "failed.json")["backup_complete"] is False


async def test_deadline_kills_native_children_and_closes_exporter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = StandIn(tmp_path, monkeypatch)
    scenario.config["hang"] = "baseline"
    monkeypatch.setattr(capture, "CAPTURE_SECONDS", 0.6)
    with pytest.raises(TimeoutError):
        await scenario.run()
    assert all(process.returncode is not None for process in scenario.processes)
    assert not (scenario.request.destination / "complete.json").exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("database_oid", "999"),
        ("server_address", "192.0.2.1"),
        ("read_only", "off"),
        ("heads", ["0001_wrong"]),
        ("role", "wrong"),
        ("server_version_num", 150001),
    ],
)
async def test_actual_source_mismatch_prevents_all_capture_children(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    scenario = StandIn(tmp_path, monkeypatch)
    actual = metadata(scenario.request)
    actual[field] = value
    scenario.config["identity"] = actual
    with pytest.raises(capture.CaptureError, match="source_identity"):
        await scenario.run()
    assert (tmp_path / "events").read_text().splitlines() == ["exported"]
    assert not (scenario.request.destination / "complete.json").exists()


async def test_existing_output_is_never_reused_or_cleaned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = StandIn(tmp_path, monkeypatch)
    scenario.request.destination.mkdir()
    sentinel = scenario.request.destination / "keep"
    sentinel.write_text(PRIVATE)
    with pytest.raises(FileExistsError):
        await scenario.run()
    assert sentinel.read_text() == PRIVATE
    assert scenario.processes == []


def test_readonly_sql_derivation_preserves_query_and_rejects_wrong_pin(tmp_path: Path) -> None:
    sql_path = Path(capture.__file__).with_name("acceptance.sql")
    sql = capture.readonly_sql(sql_path, SNAPSHOT)
    assert b"BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY" in sql
    assert b"CREATE FUNCTION" not in sql
    assert b"WITH retained AS (" in sql
    assert b"\\gexec" in sql
    assert b"LIMIT 10001" in sql
    untrusted = tmp_path / "changed.sql"
    untrusted.write_bytes(sql_path.read_bytes() + b"\n")
    with pytest.raises(capture.CaptureError, match="sql_or_snapshot_pin"):
        capture.readonly_sql(untrusted, SNAPSHOT)


@pytest.mark.parametrize("mode", [0o644, 0o400, 0o660])
def test_credentials_require_owned_regular_0600_descriptor(tmp_path: Path, mode: int) -> None:
    path = tmp_path / "synthetic.pgpass"
    path.write_text(PRIVATE)
    path.chmod(mode)
    descriptor = os.open(path, os.O_RDONLY)
    try:
        with pytest.raises(capture.CaptureError, match="private_descriptor"):
            capture.connection_env(request(tmp_path), descriptor, None)
    finally:
        os.close(descriptor)


def test_config_fd_has_closed_shape_and_no_uri_or_password_field(tmp_path: Path) -> None:
    value = {
        key: str(item) if isinstance(item, Path) else item
        for key, item in asdict(request(tmp_path)).items()
    }
    value["password"] = PRIVATE
    path = tmp_path / "request.json"
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    descriptor = os.open(path, os.O_RDONLY)
    try:
        with pytest.raises(capture.CaptureError, match="request_shape"):
            capture.read_request(descriptor)
    finally:
        os.close(descriptor)


def test_plaintext_requires_explicit_approval_and_allows_managed_endpoint(tmp_path: Path) -> None:
    with pytest.raises(capture.CaptureError, match="explicit_plaintext_approval_required"):
        replace(request(tmp_path), host="source.example.test", plaintext_approval=None)
    objects = fixture_data()["objects"]
    assert isinstance(objects, list)
    assert len(objects) == RENDITIONS


async def test_wrong_client_major_does_not_open_a_source_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = StandIn(tmp_path, monkeypatch)
    scenario.config["client_version"] = "15.8"
    with pytest.raises(capture.CaptureError, match="client_major"):
        await scenario.run()
    assert not (tmp_path / "events").exists()
    assert not (scenario.request.destination / "complete.json").exists()


@pytest.mark.parametrize("problem", ["wrong_head", "early_exporter_exit"])
async def test_lost_exporter_or_invalid_baseline_never_publishes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    problem: str,
) -> None:
    scenario = StandIn(tmp_path, monkeypatch)
    scenario.config[problem] = True
    with pytest.raises(capture.CaptureError, match=r"baseline_head|exporter_lost"):
        await scenario.run()
    assert not (scenario.request.destination / "complete.json").exists()
    assert all(process.returncode is not None for process in scenario.processes)


def test_tls_cannot_use_default_root_or_client_credentials(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.pgpass"
    path.write_text(PRIVATE)
    path.chmod(0o600)
    fd = os.open(path, os.O_RDONLY)
    try:
        req = replace(request(tmp_path), host="db.example.test", sslmode="verify-full")
        with pytest.raises(capture.CaptureError, match="explicit_ca_required"):
            capture.connection_env(req, fd, None)
        env = capture.connection_env(req, fd, fd)
        assert env["PGSSLROOTCERT"] == f"/proc/self/fd/{fd}"
        assert env["PGSSLCERT"] == "/nonexistent/client.crt"
        assert env["PGSSLKEY"] == "/nonexistent/client.key"
        assert env["PGGSSENCMODE"] == "disable"
    finally:
        os.close(fd)


def test_valid_closed_request_is_read_through_private_descriptor(tmp_path: Path) -> None:
    req = request(tmp_path)
    value = {
        key: str(item) if isinstance(item, Path) else item for key, item in asdict(req).items()
    }
    path = tmp_path / "request.json"
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    fd = os.open(path, os.O_RDONLY)
    try:
        assert capture.read_request(fd) == req
    finally:
        os.close(fd)


def test_publication_refuses_collision_and_no_completion_is_linked(tmp_path: Path) -> None:
    capture.save(tmp_path / "source.dump.part", b"PGDMPsynthetic")
    capture.save(tmp_path / "baseline.json.part", b"synthetic")
    capture.save(tmp_path / "complete.json.part", b"synthetic")
    capture.save(tmp_path / "baseline.json", b"KEEP")
    with pytest.raises(FileExistsError):
        capture.publish(tmp_path)
    assert (tmp_path / "baseline.json").read_bytes() == b"KEEP"
    assert not (tmp_path / "complete.json").exists()


async def test_cancellation_closes_owned_source_and_capture_processes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = StandIn(tmp_path, monkeypatch)
    scenario.config["hang"] = "baseline"
    running = asyncio.create_task(scenario.run())
    await asyncio.wait_for(scenario.baseline_spawned.wait(), 2)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert all(process.returncode is not None for process in scenario.processes)
    assert not (scenario.request.destination / "complete.json").exists()
    assert (scenario.request.destination / "failed.json").exists()


async def test_dump_size_bound_fails_without_any_completed_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = StandIn(tmp_path, monkeypatch)
    monkeypatch.setattr(capture, "MAX_DUMP_BYTES", 20)
    with pytest.raises(capture.CaptureError, match="archive_bound"):
        await scenario.run()
    assert not (scenario.request.destination / "complete.json").exists()
    assert all(process.returncode is not None for process in scenario.processes)


def test_durability_failure_removes_own_completion_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("source.dump", "baseline.json", "complete.json"):
        capture.save(tmp_path / (name + ".part"), b"synthetic")
    original = os.fsync
    calls = 0
    final_directory_flush = 2

    def fail_final_flush(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == final_directory_flush:
            raise OSError("synthetic_local_durability_failure")
        original(descriptor)

    monkeypatch.setattr(os, "fsync", fail_final_flush)
    with pytest.raises(OSError, match="synthetic_local_durability_failure"):
        capture.publish(tmp_path)
    assert not (tmp_path / "complete.json").exists()


def test_managed_nat_and_explicit_plaintext_approval_are_separate_pins(tmp_path: Path) -> None:
    req = replace(request(tmp_path), host="managed.example.test", endpoint_address="192.0.2.8")
    result = capture.identity(json.dumps(metadata(req)).encode(), req)
    assert result["server_address"] == "10.20.30.40"
    assert result["server_port"] == req.server_port
    assert result["system_identifier"] is None
    assert result["cluster_identifier_verified"] is False


async def test_preflight_reports_missing_read_capability_without_starting_dump(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = StandIn(tmp_path, monkeypatch)
    actual = metadata(scenario.request)
    caps = actual["capabilities"]
    assert isinstance(caps, dict)
    caps["unreadable_tables"] = 1
    scenario.config["identity"] = actual
    (tmp_path / "native.json").write_text(json.dumps(scenario.config))
    try:
        await capture.capture(scenario.request, scenario.descriptor, preflight=True)
    finally:
        os.close(scenario.descriptor)
    report = load(scenario.request.destination / "preflight.json")
    assert report["status"] == "source_preflight"
    assert not (scenario.request.destination / "complete.json").exists()
    assert (tmp_path / "events").read_text().splitlines() == ["exported", "released"]


async def test_capture_refuses_known_missing_table_privileges_before_dump(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = StandIn(tmp_path, monkeypatch)
    actual = metadata(scenario.request)
    caps = actual["capabilities"]
    assert isinstance(caps, dict)
    caps["unreadable_tables"] = 1
    scenario.config["identity"] = actual
    with pytest.raises(capture.CaptureError, match="source_read_capabilities"):
        await scenario.run()
    assert not (scenario.request.destination / "complete.json").exists()


def test_observed_full_host_mask_is_normalized_without_allowing_network_pins(
    tmp_path: Path,
) -> None:
    req = request(tmp_path)
    actual = metadata(req)
    actual["server_address"] = req.server_address + "/32"
    observed = capture.identity(json.dumps(actual).encode(), req)
    assert observed["server_address"] == req.server_address
    assert observed["server_address_raw"] == actual["server_address"]
    with pytest.raises(capture.CaptureError, match="exact_server_address_required"):
        replace(req, server_address="10.20.30.0/24")


async def test_available_pinned_cluster_id_is_read_and_verified(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = StandIn(tmp_path, monkeypatch)
    scenario.request = replace(scenario.request, system_identifier="12345")
    actual = metadata(scenario.request)
    caps = actual["capabilities"]
    assert isinstance(caps, dict)
    caps["control_system"] = True
    scenario.config["identity"] = actual
    await scenario.run()
    source = load(scenario.request.destination / "complete.json")["source"]
    assert isinstance(source, dict)
    assert source["system_identifier"] == "12345"
    assert source["cluster_identifier_verified"] is True
    assert source["identity_limitations"] == []
