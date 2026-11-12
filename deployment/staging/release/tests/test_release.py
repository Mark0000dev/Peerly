"""Synthetic orchestration faults; these never establish deployment readiness."""

from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING

import pytest
from deployment.staging.release.data import HTTP_OK, Object, RejectedError, array, obj, rows, text
from deployment.staging.release.release import (
    ASSETS,
    BACKEND,
    FRONTEND,
    ORIGIN,
    RELEASE,
    ROLES,
    SCHEMA,
    SOURCE,
    Image,
    Promotion,
    Snapshot,
    Target,
    merged_assets,
)

if TYPE_CHECKING:
    from collections.abc import Callable

PREVIOUS_SHA = "a" * 40
SELECTED_SHA = "b" * 40
TWO_PHASES = 2


def image(role: str, char: str) -> Image:
    return Image(
        role,
        char * 40,
        "ghcr.io/mark0000dev/peerly-" + role + "@sha256:" + char * 64,
        "sha256:" + char * 64,
    )


def proof(img: Image) -> Object:
    return {
        "run": {
            "repository": {"full_name": "Mark0000dev/Peerly"},
            "head_repository": {"full_name": "Mark0000dev/Peerly"},
            "head_sha": img.sha,
            "head_branch": "main",
            "event": "push",
            "path": ".github/workflows/"
            + ("backend.yml" if img.role == "backend" else "frontend-image.yml"),
            "id": 100,
            "run_attempt": 1,
            "status": "completed",
            "conclusion": "success",
        },
        "published": {
            "source_sha": img.sha,
            "image": img.reference,
            "digest": img.reference.split("@")[1],
            "smoked_image_id": img.config,
        },
        "labels": {
            "org.opencontainers.image.source": SOURCE,
            "org.opencontainers.image.revision": img.sha,
        },
    }


class Fake:
    def __init__(self) -> None:
        self.previous = {r: image(r, "a") for r in ("backend", "frontend")}
        self.candidate = {r: image(r, "b") for r in ("backend", "frontend")}
        self.all_images = {
            i.reference: i for i in [*self.previous.values(), *self.candidate.values()]
        }
        env = {
            BACKEND: self.previous["backend"].reference,
            FRONTEND: self.previous["frontend"].reference,
            ASSETS: json.dumps([{"release_id": PREVIOUS_SHA, "asset_ids": [0]}]),
            "KEEP_VALUE": "synthetic-must-survive",
            RELEASE: PREVIOUS_SHA,
            "PEERLY_HOST": "peerly-staging.aleksei-orlov.dev",
        }
        self.snapshot = Snapshot(
            {
                "Id": 4,
                "EndpointId": 1,
                "Name": "peerly-staging",
                "Type": 2,
                "Status": 1,
                "Env": [{"name": k, "value": v} for k, v in env.items()],
            },
            "synthetic full compose",
        )
        self.writes: list[Object] = []
        self.phases: list[str] = []
        self.fail_write = False
        self.mutation: Callable[[Object], None] | None = None
        self.extra_service = ""
        self.release: Object = {
            "releaseId": SELECTED_SHA,
            "origin": ORIGIN,
            "assets": [{"basename": "main-ABC.js", "assetId": 0}],
        }

    def request(self, path: str, data: Object | None = None, method: str | None = None) -> Object:
        if method == "PUT":
            assert path == "/api/stacks/4?endpointId=1"
            assert data is not None
            assert set(data) == {"StackFileContent", "Env", "Prune", "PullImage"}
            assert data["Prune"] is False
            assert data["PullImage"] is False
            self.writes.append(copy.deepcopy(data))
            self.snapshot.content = text(data["StackFileContent"])
            self.snapshot.stack["Env"] = copy.deepcopy(data["Env"])
            if self.fail_write:
                raise TimeoutError("synthetic secret must not escape")
            return {}
        if path.endswith("/file"):
            return {"StackFileContent": self.snapshot.content}
        return copy.deepcopy(self.snapshot.stack)

    def frontend_release(self, selected: Image) -> Object:
        assert selected == self.candidate["frontend"]
        return self.release

    def render(self, snapshot: Snapshot) -> Object:
        env = snapshot.env()
        services: Object = {
            r: {
                "image": env[FRONTEND if r == "frontend" else BACKEND],
                "environment": ({ASSETS: env[ASSETS]} if r == "api" else {})
                | ({"OBSERVABILITY__RELEASE": env[RELEASE]} if r != "frontend" else {}),
                "read_only": True,
            }
            for r in ROLES
        }
        if self.extra_service:
            services[self.extra_service] = {"image": env[BACKEND]}
        return {"services": services, "networks": {"application": {"driver": "bridge"}}}

    def checkpoint(self, phase: str) -> None:
        self.phases.append(phase)

    def safety(self) -> Object:
        return self.evidence()

    def evidence(self) -> Object:
        env = self.snapshot.env()
        roles: Object = {}
        for role in ROLES:
            img = self.all_images[env[FRONTEND if role == "frontend" else BACKEND]]
            roles[role] = {
                "reference": img.reference,
                "config": img.config,
                "revision": img.sha,
                "source": SOURCE,
                "running": True,
                "replicas": 1,
                "progress_after_start": True,
            }
        result: Object = {
            "schema": SCHEMA,
            "external_delivery": "stopped",
            "ai": {"container_id": "canonical", "started_at": "unchanged"},
            "roles": roles,
            "ready_path": "/api/ready",
            "ready_status": HTTP_OK,
            "approved_releases": array(env[ASSETS]),
            "served_release_id": self.all_images[env[FRONTEND]].sha,
            "same_origin_contract": True,
            "authenticated_smoke": True,
        }
        if self.mutation:
            self.mutation(result)
        return result


@pytest.fixture
def fake() -> Fake:
    return Fake()


def promotion(fake: Fake) -> Promotion:
    proofs: Object = {r: proof(i) for r, i in fake.candidate.items()}
    return Promotion(
        fake,
        Target(4, 1, "peerly-staging"),
        fake.candidate["backend"],
        fake.candidate["frontend"],
        proofs,
    )


def test_two_phase_and_rollback_preserve_all_environment(fake: Fake) -> None:
    p = promotion(fake)
    baseline = fake.evidence()
    final = p.promote(fake.release, baseline, fake.previous)
    assert len(fake.writes) == TWO_PHASES
    first = Snapshot(fake.snapshot.stack | {"Env": fake.writes[0]["Env"]}, final.content)
    assert first.env()[FRONTEND] == fake.previous["frontend"].reference
    assert first.env()[BACKEND] == fake.candidate["backend"].reference
    assert final.env()["KEEP_VALUE"] == "synthetic-must-survive"
    assert len(array(final.env()[ASSETS])) == TWO_PHASES
    assert p.phase == "verified"
    reverted = p.rollback(final, fake.previous, baseline, SCHEMA)
    assert reverted.env()[BACKEND] == fake.previous["backend"].reference
    assert len(array(reverted.env()[ASSETS])) == TWO_PHASES
    assert p.phase == "rollback_verified"


def test_uncertain_write_is_single_attempt(fake: Fake) -> None:
    fake.fail_write = True
    p = promotion(fake)
    with pytest.raises(RejectedError, match=r"^write_uncertain_reconcile_before_retry$"):
        p.promote(fake.release, fake.evidence(), fake.previous)
    assert len(fake.writes) == 1
    with pytest.raises(RejectedError, match="attempt_already_started"):
        p.promote(fake.release, fake.evidence(), fake.previous)


def test_cas_and_checkpoint_failure(fake: Fake, monkeypatch: pytest.MonkeyPatch) -> None:
    before = copy.deepcopy(fake.snapshot)
    obj(rows(fake.snapshot.stack["Env"])[0])["value"] = "changed"
    with pytest.raises(RejectedError, match="stale_stack_or_environment"):
        promotion(fake).put(
            before, before.changed({BACKEND: fake.candidate["backend"].reference}), "test"
        )
    assert not fake.writes
    fake.snapshot = before

    def fail(_phase: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(fake, "checkpoint", fail)
    with pytest.raises(OSError, match="disk full"):
        promotion(fake).promote(fake.release, fake.evidence(), fake.previous)
    assert not fake.writes


@pytest.mark.parametrize(
    "target",
    [Target(5, 1, "peerly-staging"), Target(4, 2, "peerly-staging"), Target(4, 1, "production")],
)
def test_wrong_target(target: Target) -> None:
    with pytest.raises(RejectedError, match="target"):
        target.validate()


@pytest.mark.parametrize(
    ("area", "key", "value"),
    [
        ("run", "head_sha", "c" * 40),
        ("run", "event", "pull_request"),
        ("run", "conclusion", "failure"),
        ("run", "head_branch", "other"),
        ("run", "path", ".github/workflows/backend-image.yml"),
        ("published", "digest", "sha256:" + "f" * 64),
        ("published", "smoked_image_id", "sha256:" + "f" * 64),
        ("labels", "org.opencontainers.image.revision", "c" * 40),
        ("labels", "org.opencontainers.image.source", "other"),
    ],
)
def test_quality_identity(area: str, key: str, value: str, fake: Fake) -> None:
    selected = fake.candidate["backend"]
    data = proof(selected)
    obj(data[area])[key] = value
    with pytest.raises(RejectedError):
        selected.validate(obj(data["run"]), obj(data["published"]), obj(data["labels"]))


@pytest.mark.parametrize(
    "reference",
    [
        "ghcr.io/mark0000dev/peerly-backend:latest",
        "ghcr.io/other/peerly-backend@sha256:" + "b" * 64,
    ],
)
def test_mutable_or_wrong_repository(reference: str, fake: Fake) -> None:
    selected = Image("backend", SELECTED_SHA, reference, "sha256:" + "b" * 64)
    data = proof(fake.candidate["backend"])
    with pytest.raises(RejectedError, match="image_digest"):
        selected.validate(obj(data["run"]), obj(data["published"]), obj(data["labels"]))


@pytest.mark.parametrize(
    "delta",
    [
        {"origin": "https://other.invalid"},
        {"releaseId": "c" * 40},
        {"assets": [{"basename": "../x.js", "assetId": 0}]},
        {"assets": [{"basename": "x.js", "assetId": True}]},
    ],
)
def test_asset_validation(delta: Object, fake: Fake) -> None:
    with pytest.raises(RejectedError):
        merged_assets(fake.snapshot.env()[ASSETS], fake.release | delta, SELECTED_SHA)


def test_rebind(fake: Fake) -> None:
    with pytest.raises(RejectedError, match="asset_rebind"):
        merged_assets(
            json.dumps([{"release_id": SELECTED_SHA, "asset_ids": [1]}]), fake.release, SELECTED_SHA
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [("schema", "0061"), ("ai", {"container_id": "recreated"}), ("external_delivery", "running")],
)
def test_unsafe_runtime(field: str, value: object, fake: Fake) -> None:
    baseline = fake.evidence()
    fake.mutation = lambda result: result.update({field: value})
    with pytest.raises(RejectedError):
        promotion(fake).promote(fake.release, baseline, fake.previous)
    assert not fake.writes


def test_worker_progress_required(fake: Fake) -> None:
    fake.mutation = lambda result: obj(obj(result["roles"])["media"]).update(
        progress_after_start=False
    )
    with pytest.raises(RejectedError, match="worker_progress_missing"):
        promotion(fake).promote(fake.release, fake.evidence(), fake.previous)
    assert not fake.writes


def test_ai_in_compose_rejected(fake: Fake) -> None:
    fake.extra_service = "ai"
    with pytest.raises(RejectedError, match="non_core_service"):
        promotion(fake).promote(fake.release, fake.evidence(), fake.previous)
    assert not fake.writes


def test_map_postcondition_blocks_frontend(fake: Fake) -> None:
    def mutate(result: Object) -> None:
        if fake.writes:
            result["approved_releases"] = []

    fake.mutation = mutate
    with pytest.raises(RejectedError, match="api_asset_map"):
        promotion(fake).promote(fake.release, fake.evidence(), fake.previous)
    assert len(fake.writes) == 1


def test_rollback_drift_and_schema(fake: Fake) -> None:
    p = promotion(fake)
    baseline = fake.evidence()
    final = p.promote(fake.release, baseline, fake.previous)
    with pytest.raises(RejectedError, match="rollback_schema_compatibility"):
        p.rollback(final, fake.previous, baseline, "0061")
    obj(rows(fake.snapshot.stack["Env"])[0])["value"] = "drift"
    with pytest.raises(RejectedError, match="rollback_drift"):
        p.rollback(final, fake.previous, baseline, SCHEMA)
    assert len(fake.writes) == TWO_PHASES


def test_rollback_can_repair_broken_current_ui(fake: Fake, monkeypatch: pytest.MonkeyPatch) -> None:
    p = promotion(fake)
    baseline = fake.evidence()
    final = p.promote(fake.release, baseline, fake.previous)
    original = fake.evidence

    def broken_until_rollback() -> Object:
        if len(fake.writes) == TWO_PHASES:
            raise RejectedError("broken_current_ui")
        return original()

    monkeypatch.setattr(fake, "safety", lambda: baseline)
    monkeypatch.setattr(fake, "evidence", broken_until_rollback)
    result = p.rollback(final, fake.previous, baseline, SCHEMA)
    assert result.env()[BACKEND] == fake.previous["backend"].reference
    assert p.phase == "rollback_verified"
