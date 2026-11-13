"""Synthetic stateful Portainer wires exercise actual lifecycle/phase CAS code.

No Docker process, provider, host or DB connection is made. These are regressions,
never live readiness/activation receipts.
"""

from __future__ import annotations

import argparse
import copy
import json
import struct
from dataclasses import asdict
from typing import TYPE_CHECKING
from urllib.parse import unquote

import httpx
import pytest
from deployment.staging.release.cli import recover
from deployment.staging.release.data import Object, RejectedError, obj, rows, text
from deployment.staging.release.external_lifecycle import EXTERNAL_IMAGE, EXTERNAL_RELEASE
from deployment.staging.release.external_policy import ExternalPolicy, save_private
from deployment.staging.release.external_probe import EXTERNAL_DATABASE, EXTERNAL_REGISTRY
from deployment.staging.release.journal import Journal
from deployment.staging.release.portainer import DOCKER, Portainer
from deployment.staging.release.providers import Package
from deployment.staging.release.release import SOURCE, Image, Snapshot
from deployment.staging.release.runtime import ObservationInputs, Runtime
from deployment.staging.release.tests.test_external import receipt
from deployment.staging.release.tests.test_external_signals import metrics
from deployment.staging.release.tests.test_release import Fake, promotion, proof
from deployment.staging.release.transport import Http

if TYPE_CHECKING:
    from pathlib import Path

    from deployment.staging.release.external_lifecycle import ExternalLifecycle

OLD_ID = "1" * 64
NEW_ID = "2" * 64
API_ID = "f" * 64
EXEC_ID = "e" * 64
DATABASE_URL = "postgresql+asyncpg://synthetic/peerly_staging"


def container(image: Image, cid: str) -> Object:
    return {
        "Id": cid,
        "Image": image.config,
        "State": {
            "Running": True,
            "Paused": False,
            "Restarting": False,
            "Pid": 321,
            "StartedAt": "start-" + cid,
            "FinishedAt": "",
            "ExitCode": 0,
            "OOMKilled": False,
            "Error": "",
        },
        "HostConfig": {"ReadonlyRootfs": True},
        "Config": {
            "Image": image.reference,
            "Hostname": cid[:12],
            "User": "10001:10001",
            "Cmd": ["python", "-m", "studymate.external_delivery_worker"],
            "Env": [
                "DATABASE_URL=" + DATABASE_URL,
                "UMAMI__HOSTNAME=peerly-staging.aleksei-orlov.dev",
                "UMAMI__REVISION=1",
                "UMAMI__ORIGIN=https://synthetic.invalid",
                "UMAMI__WEBSITE_ID=11111111-1111-1111-1111-111111111111",
                "OBSERVABILITY__RELEASE=" + image.sha,
            ],
            "Labels": {
                "com.docker.compose.project": "peerly-staging",
                "com.docker.compose.service": "external_delivery",
                "org.opencontainers.image.source": SOURCE,
                "org.opencontainers.image.revision": image.sha,
            },
        },
    }


class Wire:
    def __init__(self, fake: ActiveFake) -> None:
        self.fake = fake
        self.old = container(fake.previous["backend"], OLD_ID)
        self.current = self.old
        self.calls: list[tuple[str, str]] = []
        self.result: Object = {}
        self.cycles = 0
        self.database_schema = "0060_report_triage"
        self.exit_code = 0
        self.ignore_term = False
        self.drift_after_term = False
        self.cas_drift_after_term = False
        self.drift_registry = False
        self.keep_old = True
        self.extra = False
        self.generation = 1

    def recreate(self) -> None:
        env = self.fake.snapshot.env()
        image = self.fake.all_images[env[EXTERNAL_IMAGE]]
        self.generation += 1
        self.current = container(image, str(self.generation) * len(NEW_ID))

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = unquote(request.url.path)
        self.calls.append((request.method, path))
        if path == "/peerly-observe/metrics/application":
            self.cycles += 1
            revision = text(
                obj(obj(self.current["Config"])["Labels"])["org.opencontainers.image.revision"]
            )
            return httpx.Response(
                200, content=metrics(str(self.cycles)).replace(b"synthetic", revision.encode())
            )
        if path.startswith(DOCKER + "/images/"):
            reference = path.removeprefix(DOCKER + "/images/").removesuffix("/json")
            image = self.fake.all_images[reference]
            return httpx.Response(
                200,
                json={
                    "Id": image.config,
                    "Config": {
                        "Labels": {
                            "org.opencontainers.image.source": SOURCE,
                            "org.opencontainers.image.revision": image.sha,
                        }
                    },
                },
            )
        if path == DOCKER + "/containers/json":
            containers = [self.current]
            if self.current is not self.old and self.keep_old:
                containers.append(self.old)
            result = [
                {
                    "Id": c["Id"],
                    "Command": "python -m studymate.external_delivery_worker",
                    "Labels": obj(c["Config"])["Labels"],
                    "State": "running" if obj(c["State"])["Running"] else "exited",
                }
                for c in containers
            ]
            result.append(
                {
                    "Id": API_ID,
                    "State": "running",
                    "Command": "python -m studymate.server",
                    "Labels": {
                        "com.docker.compose.project": "peerly-staging",
                        "com.docker.compose.service": "api",
                    },
                }
            )
            if self.extra:
                result.append(result[0] | {"Id": "3" * 64})
            return httpx.Response(200, json=result)
        return self.control(request, path)

    def control(self, request: httpx.Request, path: str) -> httpx.Response:
        if path.endswith("/kill"):
            assert request.method == "POST"
            assert request.url.params.get("signal") == "SIGTERM"
            assert path == DOCKER + f"/containers/{text(self.current['Id'])}/kill"
            if self.ignore_term:
                return httpx.Response(204)
            if self.drift_after_term:
                self.drift_registry = True
            if self.cas_drift_after_term:
                for entry in rows(self.fake.snapshot.stack["Env"]):
                    if obj(entry)["name"] == "KEEP_VALUE":
                        obj(entry)["value"] = "concurrent-operator-change"
            obj(self.current["State"]).update(
                Running=False, Pid=0, FinishedAt="finish", ExitCode=self.exit_code
            )
            return httpx.Response(204)
        if path.endswith("/start") and path.startswith(DOCKER + "/containers/"):
            assert request.method == "POST"
            assert path == DOCKER + f"/containers/{OLD_ID}/start"
            obj(self.old["State"]).update(
                Running=True, Pid=456, StartedAt="restored", FinishedAt=""
            )
            self.current = self.old
            return httpx.Response(204)
        return self.probe(request, path)

    def probe(self, request: httpx.Request, path: str) -> httpx.Response:
        if path.endswith("/exec"):
            payload = json.loads(request.content)
            script = payload["Cmd"][2]
            assert script in {EXTERNAL_DATABASE, EXTERNAL_REGISTRY}
            registered = [] if self.drift_registry else receipt()["destinations"]
            self.result = {
                "heads": [self.database_schema],
                "database_name": "peerly_staging",
                "registered": registered,
            }
            if script == EXTERNAL_DATABASE:
                self.result["configured"] = receipt()["destinations"]
            return httpx.Response(201, json={"Id": EXEC_ID})
        if path == DOCKER + f"/exec/{EXEC_ID}/start":
            data = json.dumps(self.result).encode()
            return httpx.Response(
                200, content=b"\x01\x00\x00\x00" + struct.pack(">I", len(data)) + data
            )
        if path == DOCKER + f"/exec/{EXEC_ID}/json":
            return httpx.Response(200, json={"Running": False, "ExitCode": 0})
        assert request.method == "GET"
        if path == DOCKER + f"/containers/{API_ID}/json":
            image = self.fake.all_images[self.fake.snapshot.env()["PEERLY_BACKEND_IMAGE"]]
            return httpx.Response(
                200,
                json={
                    "Id": API_ID,
                    "Image": image.config,
                    "Config": {"Env": ["DATABASE_URL=" + DATABASE_URL]},
                },
            )
        if path == DOCKER + f"/containers/{text(self.current['Id'])}/json":
            return httpx.Response(200, json=self.current)
        assert path == DOCKER + f"/containers/{OLD_ID}/json"
        return httpx.Response(200, json=self.old)


class ActiveFake(Fake):
    def __init__(self) -> None:
        super().__init__()
        self.external: ExternalLifecycle | None = None
        self.journal: Journal | None = None
        self.after_write_failure = False
        self.wire = Wire(self)
        env = [
            {"name": EXTERNAL_IMAGE, "value": self.previous["backend"].reference},
            {"name": EXTERNAL_RELEASE, "value": self.previous["backend"].sha},
            {"name": "PEERLY_DATABASE_URL", "value": DATABASE_URL},
        ]
        self.snapshot.stack["Env"] = rows(self.snapshot.stack["Env"]) + env

    def render(self, snapshot: Snapshot) -> Object:
        rendered = super().render(snapshot)
        obj(rendered["services"])["external_delivery"] = {
            "image": snapshot.env()[EXTERNAL_IMAGE],
            "pull_policy": "never",
            "deploy": {"replicas": 1},
            "command": ["python", "-m", "studymate.external_delivery_worker"],
            "environment": {"OBSERVABILITY__RELEASE": snapshot.env()[EXTERNAL_RELEASE]},
        }
        return rendered

    def request(self, path: str, data: Object | None = None, method: str | None = None) -> Object:
        old = self.snapshot.env()[EXTERNAL_IMAGE]
        result = super().request(path, data, method)
        if method == "PUT" and self.snapshot.env()[EXTERNAL_IMAGE] != old:
            self.wire.recreate()
            if self.after_write_failure:
                raise TimeoutError("synthetic lost response")
        return result

    def checkpoint(self, phase: str) -> None:
        super().checkpoint(phase)
        if self.journal is not None:
            self.journal.checkpoint(phase)

    def evidence(self) -> Object:
        evidence = super().evidence()
        assert self.external is not None
        external = self.external.evidence(self.snapshot)
        evidence["external_delivery"] = external
        obj(evidence["roles"])["external_delivery"] = external
        return evidence


class SyntheticRuntime(Runtime):
    def __init__(self, fake: ActiveFake, journal: Journal, inputs: ObservationInputs) -> None:
        self.fake = fake
        fake.journal = journal
        http = Http(httpx.MockTransport(fake.wire.handle))
        packages = {r: Package(i, proof(i), fake.release) for r, i in fake.candidate.items()}
        super().__init__(
            Portainer(http, "https://synthetic.invalid", "synthetic"),
            http,
            journal,
            packages,
            inputs,
        )

    def render(self, snapshot: Snapshot) -> Object:
        return self.fake.render(snapshot)

    def snapshot(self) -> Snapshot:
        return copy.deepcopy(self.fake.snapshot)


def schema_evidence(fake: ActiveFake) -> Object:
    return {
        i.sha: {
            "image": i.reference,
            "config": i.config,
            "database_schema": "0060_report_triage",
            "image_schema_head": "0060_report_triage",
            "entrypoint": "studymate.external_delivery_worker",
            "sinks": ["umami"],
            "evidence_id": "synthetic-witness-not-acceptance",
            "witness_kind": "immutable_image_role_compatibility",
        }
        for i in (fake.previous["backend"], fake.candidate["backend"])
    }


def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[ActiveFake, SyntheticRuntime]:
    monkeypatch.setattr("deployment.staging.release.external_lifecycle.time.sleep", lambda _: None)
    fake = ActiveFake()
    accepted = receipt()
    actual = fake.wire.old
    accepted.update(
        container_id=OLD_ID,
        image_config=actual["Image"],
        started_at=obj(actual["State"])["StartedAt"],
        pid=321,
        config=actual["Config"],
        host_config=actual["HostConfig"],
    )
    policy = ExternalPolicy.parse(
        {
            "version": 1,
            "accepted": accepted,
            "service_spec": obj(fake.render(fake.snapshot)["services"])["external_delivery"],
            "upgrade_source": fake.candidate["backend"].sha,
            "core_compatible_sources": [
                fake.previous["backend"].sha,
                fake.candidate["backend"].sha,
            ],
            "role_schema_evidence": schema_evidence(fake),
            "compatible_sources": [fake.previous["backend"].sha, fake.candidate["backend"].sha],
        }
    )
    tmp_path.mkdir(exist_ok=True)
    attempt = tmp_path / "attempt"
    attempt.mkdir()
    inputs = ObservationInputs(
        "https://synthetic.invalid",
        "synthetic",
        "synthetic",
        "synthetic",
        "c" * 64,
        "peerly_staging",
        lambda: None,
        policy,
    )
    runtime = SyntheticRuntime(fake, Journal(attempt / "journal"), inputs)
    fake.external = runtime.external
    return fake, runtime


def test_complete_core_then_external_upgrade_and_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake, runtime = setup(tmp_path, monkeypatch)
    p = promotion(fake)
    p.external = runtime.external
    try:
        baseline = fake.evidence()
        previous = fake.previous | {"external": fake.previous["backend"]}
        final = p.promote(fake.release, baseline, previous)
        assert final.env()[EXTERNAL_IMAGE] == fake.candidate["backend"].reference
        assert final.env()["KEEP_VALUE"] == "synthetic-must-survive"
        assert (tmp_path / "attempt" / "external-exit.private.json").exists()
        assert fake.wire.calls.count(("POST", DOCKER + f"/containers/{OLD_ID}/kill")) == 1
        # Separate rollback attempt as in CLI, retaining the same persistent lock root.
        rollback_dir = tmp_path / "rollback"
        rollback_dir.mkdir()
        runtime.journal.close()
        runtime.journal = Journal(rollback_dir / "journal")
        assert runtime.external is not None
        runtime.external.directory = rollback_dir
        reverted = p.rollback(final, previous, baseline, "0060_report_triage")
        assert reverted.env()[EXTERNAL_IMAGE] == fake.previous["backend"].reference
        assert reverted.env()[EXTERNAL_RELEASE] == fake.previous["backend"].sha
    finally:
        runtime.journal.close()


@pytest.mark.parametrize("failure", ["forced_exit", "extra_executor", "registry"])
def test_unknown_or_unsafe_transition_never_writes_stack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    fake, runtime = setup(tmp_path, monkeypatch)
    p = promotion(fake)
    p.external = runtime.external
    assert runtime.external is not None
    if failure == "forced_exit":
        fake.wire.exit_code = 137
    elif failure == "extra_executor":
        fake.wire.extra = True
    else:
        fake.wire.drift_registry = True
    try:
        with pytest.raises(RejectedError):
            runtime.external.upgrade(p, fake.snapshot, fake.candidate["backend"])
        assert not fake.writes
    finally:
        runtime.journal.close()


@pytest.mark.parametrize("rollback", [False, True])
def test_cli_recovery_after_lost_put_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rollback: bool
) -> None:
    fake, runtime = setup(tmp_path, monkeypatch)
    p = promotion(fake)
    p.external = runtime.external
    assert runtime.external is not None
    before = copy.deepcopy(fake.snapshot)
    baseline = fake.evidence()
    directory = tmp_path / "attempt"
    save_private(
        directory / "before.private.json", {"stack": before.stack, "content": before.content}
    )
    previous = fake.previous | {"external": fake.previous["backend"]}
    save_private(
        directory / "recovery.private.json",
        {
            "sha": fake.candidate["backend"].sha,
            "baseline": baseline,
            "previous": {r: asdict(i) for r, i in previous.items()},
        },
    )
    save_private(
        tmp_path / "unresolved.json",
        {"attempt": "attempt", "sha": fake.candidate["backend"].sha, "operation": "promote"},
    )
    fake.after_write_failure = True
    try:
        with pytest.raises(RejectedError, match="write_uncertain"):
            runtime.external.upgrade(p, before, fake.candidate["backend"])
    finally:
        runtime.journal.close()
    fake.after_write_failure = False
    new_dir = tmp_path / "recovery"
    new_dir.mkdir()
    fresh = SyntheticRuntime(fake, Journal(new_dir / "journal"), runtime.inputs)
    fake.external = fresh.external
    candidate = promotion(fake)
    candidate.external = fresh.external
    args = argparse.Namespace(
        operation="rollback" if rollback else "reconcile",
        recovery=str(directory / "recovery.private.json"),
        reconcile_attempt="attempt",
        compatible_schema="0060_report_triage",
        sha=fake.candidate["backend"].sha,
    )
    try:
        result = recover(args, candidate, fresh, fake.snapshot, new_dir)
        expected = fake.previous["backend"] if rollback else fake.candidate["backend"]
        assert result.env()[EXTERNAL_IMAGE] == expected.reference
        assert not (tmp_path / "unresolved.json").exists()
        assert (tmp_path / "external-lineage.private.json").exists()
    finally:
        fresh.journal.close()


@pytest.mark.parametrize("rollback", [False, True])
def test_explicit_recovery_after_clean_exit_before_put(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rollback: bool
) -> None:
    fake, runtime = setup(tmp_path, monkeypatch)
    p = promotion(fake)
    p.external = runtime.external
    assert runtime.external is not None
    # Inject failure precisely at fresh phase CAS after actual owned TERM/clean exit.
    fake.wire.cas_drift_after_term = True
    before = copy.deepcopy(fake.snapshot)
    try:
        with pytest.raises(RejectedError, match="stale_stack"):
            runtime.external.upgrade(p, before, fake.candidate["backend"])
        assert not fake.writes
    finally:
        runtime.journal.close()
    # Parent restores ONLY the independently reviewed source Env drift before
    # explicit reconciliation; recovery never overwrites unknown operator state.
    fake.snapshot = before
    fake.wire.cas_drift_after_term = False
    new_dir = tmp_path / "recovery"
    new_dir.mkdir()
    fresh = SyntheticRuntime(fake, Journal(new_dir / "journal"), runtime.inputs)
    fake.external = fresh.external
    candidate = promotion(fake)
    candidate.external = fresh.external
    assert fresh.external is not None
    try:
        result = fresh.external.reconcile(
            candidate, before, tmp_path / "attempt", rollback=rollback
        )
        expected = fake.previous["backend"] if rollback else fake.candidate["backend"]
        assert result.env()[EXTERNAL_IMAGE] == expected.reference
        starts = [
            path
            for method, path in fake.wire.calls
            if method == "POST" and path.endswith("/start") and "/containers/" in path
        ]
        assert bool(starts) == rollback
    finally:
        fresh.journal.close()


@pytest.mark.parametrize("failure", ["timeout", "registry_after_term"])
def test_no_force_kill_or_stack_write_on_unclean_or_changed_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    fake, runtime = setup(tmp_path, monkeypatch)
    p = promotion(fake)
    p.external = runtime.external
    assert runtime.external is not None
    if failure == "timeout":
        fake.wire.ignore_term = True
        monkeypatch.setattr("deployment.staging.release.external_lifecycle.GRACE_SECONDS", 0)
    else:
        fake.wire.drift_after_term = True
    try:
        with pytest.raises(RejectedError):
            runtime.external.upgrade(p, fake.snapshot, fake.candidate["backend"])
        assert not fake.writes
        assert not any(
            path.endswith("/stop") or (path.endswith("/start") and "/containers/" in path)
            for _, path in fake.wire.calls
        )
    finally:
        runtime.journal.close()


def test_pinned_active_worker_survives_core_upgrade_without_signal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake, runtime = setup(tmp_path, monkeypatch)
    assert runtime.external is not None
    from dataclasses import replace

    runtime.external.policy = replace(runtime.external.policy, upgrade_source="")
    p = promotion(fake)
    p.external = runtime.external
    try:
        final = p.promote(fake.release, fake.evidence(), fake.previous)
        assert final.env()[EXTERNAL_IMAGE] == fake.previous["backend"].reference
        assert fake.wire.current["Id"] == OLD_ID
        assert not any(path.endswith("/kill") for _, path in fake.wire.calls)
    finally:
        runtime.journal.close()


def test_unreviewed_external_source_rejected_before_term(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake, runtime = setup(tmp_path, monkeypatch)
    assert runtime.external is not None
    from dataclasses import replace

    runtime.external.policy = replace(
        runtime.external.policy, compatible_sources=frozenset({fake.previous["backend"].sha})
    )
    p = promotion(fake)
    p.external = runtime.external
    try:
        with pytest.raises(RejectedError, match="external_source_not_compatible"):
            runtime.external.upgrade(p, fake.snapshot, fake.candidate["backend"])
        assert not any(path.endswith("/kill") for _, path in fake.wire.calls)
    finally:
        runtime.journal.close()


def test_malformed_or_permissionless_policy_never_becomes_acceptance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deployment.staging.release.external_policy import policy

    path = tmp_path / "admission.json"
    monkeypatch.setattr("deployment.staging.release.external_policy.ACCEPTANCE_FILE", path)
    assert policy() is None
    path.write_text("{}")
    path.chmod(0o666)
    with pytest.raises(RejectedError, match="external_acceptance_file_permissions"):
        policy()
    path.unlink()
    target = tmp_path / "target"
    target.write_text("{}")
    path.symlink_to(target)
    with pytest.raises(OSError, match="symbolic links"):
        policy()


class DisabledFake(Fake):
    def __init__(self, replicas: int = 0) -> None:
        super().__init__()
        self.replicas = replicas

    def render(self, snapshot: Snapshot) -> Object:
        rendered = super().render(snapshot)
        obj(rendered["services"])["external_delivery"] = {
            "image": snapshot.env()["PEERLY_BACKEND_IMAGE"],
            "profiles": ["external-delivery"],
            "deploy": {"replicas": self.replicas},
            "command": ["python", "-m", "studymate.external_delivery_worker"],
        }
        return rendered


def test_disabled_profile_global_image_diff_keeps_zero_without_acceptance() -> None:
    fake = DisabledFake()
    p = promotion(fake)
    final = p.promote(fake.release, fake.evidence(), fake.previous)
    assert EXTERNAL_IMAGE not in final.env()
    assert EXTERNAL_RELEASE not in final.env()
    assert fake.replicas == 0


def test_unaccepted_enabled_service_is_not_an_activation_path() -> None:
    fake = DisabledFake(replicas=1)
    p = promotion(fake)
    with pytest.raises(RejectedError, match="non_core_service"):
        p.promote(fake.release, fake.evidence(), fake.previous)
    assert not fake.writes


@pytest.mark.parametrize(
    ("field", "value"),
    [("profiles", ["external-delivery"]), ("pull_policy", "always"), ("build", ".")],
)
def test_active_policy_refuses_unproven_profile_or_mutable_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: object
) -> None:
    fake, runtime = setup(tmp_path, monkeypatch)
    assert runtime.external is not None
    from deployment.staging.release.external_lifecycle import receipt as accepted_receipt

    spec = copy.deepcopy(runtime.external.policy.service_spec)
    spec[field] = value
    try:
        with pytest.raises(RejectedError, match="external_accepted_service_spec"):
            ExternalPolicy.parse(
                {
                    "version": 1,
                    "accepted": accepted_receipt(runtime.external.accepted),
                    "service_spec": spec,
                    "upgrade_source": "",
                    "core_compatible_sources": [fake.previous["backend"].sha],
                    "role_schema_evidence": {
                        fake.previous["backend"].sha: schema_evidence(fake)[
                            fake.previous["backend"].sha
                        ]
                    },
                    "compatible_sources": [fake.previous["backend"].sha],
                }
            )
    finally:
        runtime.journal.close()


def test_private_json_duplicate_keys_rejected() -> None:
    from deployment.staging.release.external_policy import decode

    with pytest.raises(RejectedError, match="external_duplicate_json_key"):
        decode(b'{"upgrade_source":"old","upgrade_source":"new"}')


def test_changed_root_admission_blocks_before_signal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import replace

    fake, runtime = setup(tmp_path, monkeypatch)
    assert runtime.external is not None
    runtime.external.policy = replace(runtime.external.policy, admission_document={"version": 1})
    monkeypatch.setattr(
        "deployment.staging.release.external_policy.protected_read", lambda _: {"version": 2}
    )
    p = promotion(fake)
    p.external = runtime.external
    try:
        with pytest.raises(RejectedError, match="external_acceptance_changed_before_write"):
            runtime.external.upgrade(p, fake.snapshot, fake.candidate["backend"])
        assert not any(path.endswith("/kill") for _, path in fake.wire.calls)
        assert not fake.writes
    finally:
        runtime.journal.close()


def test_worker_native_head_evidence_does_not_authorize_core_upgrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import replace

    fake, runtime = setup(tmp_path, monkeypatch)
    assert runtime.external is not None
    role = copy.deepcopy(runtime.external.policy.role_schema_evidence)
    obj(role[fake.candidate["backend"].sha])["image_schema_head"] = "0061_native_login"
    runtime.external.policy = replace(
        runtime.external.policy,
        core_compatible_sources=frozenset({fake.previous["backend"].sha}),
        role_schema_evidence=role,
    )
    p = promotion(fake)
    p.external = runtime.external
    try:
        with pytest.raises(RejectedError, match="external_core_source_not_reviewed"):
            p.promote(fake.release, fake.evidence(), fake.previous)
        assert not fake.writes
        assert not any(path.endswith("/kill") for _, path in fake.wire.calls)
    finally:
        runtime.journal.close()


@pytest.mark.parametrize("failure", ["live_schema", "image_config", "overlay_witness"])
def test_role_compatibility_evidence_is_specific_not_native_api_permission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    from dataclasses import replace

    from deployment.staging.release.external_lifecycle import receipt as accepted_receipt

    fake, runtime = setup(tmp_path, monkeypatch)
    assert runtime.external is not None
    policy = runtime.external.policy
    evidence = copy.deepcopy(policy.role_schema_evidence)
    p = promotion(fake)
    p.external = runtime.external
    try:
        if failure == "overlay_witness":
            obj(evidence[fake.previous["backend"].sha])["witness_kind"] = (
                "read_only_source_overlay_not_plain_image"
            )
            with pytest.raises(RejectedError, match="external_role_schema_evidence"):
                ExternalPolicy.parse(
                    {
                        "version": 1,
                        "accepted": accepted_receipt(policy.accepted),
                        "service_spec": policy.service_spec,
                        "upgrade_source": policy.upgrade_source,
                        "compatible_sources": list(policy.compatible_sources),
                        "core_compatible_sources": list(policy.core_compatible_sources),
                        "role_schema_evidence": evidence,
                    }
                )
        else:
            if failure == "live_schema":
                fake.wire.database_schema = "0061_native_login"
            else:
                obj(evidence[fake.candidate["backend"].sha])["config"] = "sha256:" + "9" * 64
                runtime.external.policy = replace(policy, role_schema_evidence=evidence)
            with pytest.raises(RejectedError):
                runtime.external.upgrade(p, fake.snapshot, fake.candidate["backend"])
        assert not fake.writes
        assert not any(path.endswith("/kill") for _, path in fake.wire.calls)
    finally:
        runtime.journal.close()
