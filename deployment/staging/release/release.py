"""Peerly core staging promotion. No credential discovery, migration or AI writes.

The coordinator supplies authenticated I/O and holds an exclusive deployment lock
across this entire operation. Portainer has no atomic conditional PUT: fresh
comparison is a conflict detector, not a distributed locking implementation.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from deployment.staging.release.data import (
    COMPOSE_TYPE,
    HTTP_OK,
    MAX_ASSETS,
    Object,
    RejectedError,
    array,
    obj,
    require,
    rows,
    text,
)

if TYPE_CHECKING:
    from deployment.staging.release.external_lifecycle import ExternalLifecycle

SOURCE = "https://github.com/Mark0000dev/Peerly"
ORIGIN = "https://peerly-staging.aleksei-orlov.dev"
SCHEMA = "0060_report_triage"
ASSETS = "PUBLIC_ASSET_RELEASES"
BACKEND = "PEERLY_BACKEND_IMAGE"
FRONTEND = "PEERLY_FRONTEND_IMAGE"
RELEASE = "PEERLY_RELEASE"
EXTERNAL_IMAGE = "EXTERNAL_DELIVERY_IMAGE"
EXTERNAL_RELEASE = "EXTERNAL_DELIVERY_RELEASE"
ROLES = frozenset({"api", "email", "media", "requests", "changes", "frontend"})


@dataclass(frozen=True)
class Image:
    role: str
    sha: str
    reference: str
    config: str

    def validate(self, run: Object, published: Object, labels: Object) -> None:
        require(self.role in {"backend", "frontend"}, "image_role")
        require(re.fullmatch(r"[0-9a-f]{40}", self.sha) is not None, "source_sha")
        prefix = "ghcr.io/mark0000dev/peerly-" + self.role + "@"
        require(
            self.reference.startswith(prefix)
            and re.fullmatch(r"sha256:[0-9a-f]{64}", self.reference[len(prefix) :]) is not None,
            "image_digest",
        )
        require(
            re.fullmatch(r"sha256:[0-9a-f]{64}", self.config) is not None,
            "image_config",
        )
        # run must be the actual GitHub API response, not an artifact's claim.
        path = ".github/workflows/" + (
            "backend.yml" if self.role == "backend" else "frontend-image.yml"
        )
        require(
            obj(run.get("repository")).get("full_name") == "Mark0000dev/Peerly"
            and obj(run.get("head_repository")).get("full_name") == "Mark0000dev/Peerly"
            and run.get("head_sha") == self.sha
            and run.get("head_branch") == "main"
            and run.get("event") == "push"
            and run.get("path") == path
            and run.get("status") == "completed"
            and run.get("conclusion") == "success"
            and type(run.get("id")) is int
            and type(run.get("run_attempt")) is int,
            "quality_run",
        )
        require(
            published.get("source_sha") == self.sha
            and published.get("image") == self.reference
            and published.get("digest") == self.reference.split("@")[1]
            and published.get("smoked_image_id") == self.config,
            "publication_binding",
        )
        require(
            labels.get("org.opencontainers.image.source") == SOURCE
            and labels.get("org.opencontainers.image.revision") == self.sha,
            "oci_labels",
        )


def merged_assets(raw: str, release: Object, sha: str) -> str:
    require(
        release.get("releaseId") == sha and release.get("origin") == ORIGIN,
        "asset_source",
    )
    assets = release.get("assets")
    if not isinstance(assets, list) or not 0 < len(assets) <= MAX_ASSETS:
        raise RejectedError("asset_count")
    require(all(isinstance(item, dict) for item in assets), "asset_shape")
    names = [text(obj(item).get("basename")) for item in assets]
    require(
        all(re.fullmatch(r"[A-Za-z0-9_.-]+\.js", n) for n in names) and names == sorted(set(names)),
        "asset_names",
    )
    require(
        all(
            type(obj(item).get("assetId")) is int and obj(item)["assetId"] == i
            for i, item in enumerate(assets)
        ),
        "asset_ids",
    )
    old = array(raw)
    seen: set[str] = set()
    for item in old:
        require(set(item) == {"release_id", "asset_ids"}, "existing_asset_shape")
        rid, ids = text(item["release_id"]), rows(item["asset_ids"])
        require(
            re.fullmatch(r"[0-9a-f]{40}", rid) is not None and rid not in seen,
            "existing_asset_shape",
        )
        require(all(type(i) is int and 0 <= i < MAX_ASSETS for i in ids), "existing_asset_shape")
        require(len(ids) == len({str(i) for i in ids}), "existing_asset_shape")
        seen.add(rid)
    new = {"release_id": sha, "asset_ids": list(range(len(assets)))}
    same = [item for item in old if item["release_id"] == sha]
    require(not same or same == [new], "asset_rebind")
    return json.dumps(old if same else [*old, new], separators=(",", ":"))


@dataclass(frozen=True)
class Target:
    stack_id: int
    endpoint_id: int
    name: str

    def validate(self) -> None:
        # This helper intentionally supports only the existing internal stack.
        require(
            (self.stack_id, self.endpoint_id, self.name) == (4, 1, "peerly-staging"),
            "target",
        )


@dataclass
class Snapshot:
    stack: Object
    content: str

    def env(self) -> dict[str, str]:
        entries = [obj(row) for row in rows(self.stack.get("Env"))]
        require(all(set(row) == {"name", "value"} for row in entries), "environment_shape")
        result = {text(row["name"]): text(row["value"]) for row in entries}
        require(len(result) == len(entries), "environment_duplicates")
        return result

    def changed(self, delta: dict[str, str]) -> Snapshot:
        require(
            set(delta) <= {BACKEND, FRONTEND, ASSETS, RELEASE, EXTERNAL_IMAGE, EXTERNAL_RELEASE},
            "environment_scope",
        )
        require(set(delta) <= self.env().keys(), "missing_environment_contract")
        result = copy.deepcopy(self)
        entries = [obj(row) for row in rows(result.stack["Env"])]
        for row in entries:
            if row["name"] in delta:
                row["value"] = delta[row["name"]]
        result.stack["Env"] = entries
        return result

    def same(self, other: Snapshot) -> bool:
        keys = ("Id", "EndpointId", "Name", "Type", "Status")
        return (
            all(self.stack.get(k) == other.stack.get(k) for k in keys)
            and self.content == other.content
            and self.stack["Env"] == other.stack["Env"]
        )


class IO(Protocol):
    def request(
        self, path: str, data: Object | None = None, method: str | None = None
    ) -> Object: ...
    def evidence(self) -> Object: ...
    def safety(self) -> Object: ...
    def render(self, snapshot: Snapshot) -> Object: ...
    def frontend_release(self, image: Image) -> Object: ...
    def checkpoint(self, phase: str) -> None: ...


class Promotion:
    """Single-use attempt; persist checkpoints durably before each PUT.

    evidence() must freshly inspect actual containers and application contracts;
    see README. No success boolean or health-only substitute is accepted.
    """

    def __init__(
        self,
        io: IO,
        target: Target,
        backend: Image,
        frontend: Image,
        proofs: Object,
    ) -> None:
        target.validate()
        self.io, self.target = io, target
        self.backend, self.frontend = backend, frontend
        require(
            backend.role == "backend"
            and frontend.role == "frontend"
            and backend.sha == frontend.sha,
            "selected_source",
        )
        for image in (backend, frontend):
            proof = obj(proofs[image.role])
            image.validate(obj(proof["run"]), obj(proof["published"]), obj(proof["labels"]))
        self.external: ExternalLifecycle | None = None
        self.started = False
        self.phase = "prepared"

    def read(self) -> Snapshot:
        t = self.target
        stack = self.io.request(f"/api/stacks/{t.stack_id}")
        content = self.io.request(f"/api/stacks/{t.stack_id}/file")["StackFileContent"]
        require(
            (
                stack.get("Id"),
                stack.get("EndpointId"),
                stack.get("Name"),
                stack.get("Type"),
                stack.get("Status"),
            )
            == (t.stack_id, t.endpoint_id, t.name, COMPOSE_TYPE, 1),
            "stack_identity",
        )
        snapshot = Snapshot(stack, text(content))
        require(
            snapshot.env().get("PEERLY_HOST") == "peerly-staging.aleksei-orlov.dev",
            "target_origin",
        )
        return snapshot

    def check_render(self, before: Snapshot, after: Snapshot) -> None:
        old, new = self.io.render(before), self.io.render(after)
        require(old.keys() == new.keys(), "compose_scope")
        require(
            {k: v for k, v in old.items() if k != "services"}
            == {k: v for k, v in new.items() if k != "services"},
            "compose_scope",
        )
        require(obj(old["services"]).keys() == obj(new["services"]).keys(), "service_scope")
        for name, value in obj(old["services"]).items():
            original = obj(value)
            require(
                "build" not in original and original.get("pull_policy") not in {"always", "build"},
                "immutable_compose_policy",
            )
            replacement = copy.deepcopy(obj(obj(new["services"])[name]))
            if name in ROLES:
                require(
                    original.get("scale", 1) == 1
                    and obj(original.get("deploy", {})).get("replicas", 1) == 1,
                    "core_replica_policy",
                )
                key = FRONTEND if name == "frontend" else BACKEND
                require(replacement.get("image") == after.env()[key], "rendered_image")
                replacement["image"] = original["image"]
                if name != "frontend":
                    environment = obj(replacement.get("environment", {}))
                    require(
                        environment.get("OBSERVABILITY__RELEASE") == after.env()[RELEASE],
                        "telemetry_release",
                    )
                    environment["OBSERVABILITY__RELEASE"] = obj(original["environment"])[
                        "OBSERVABILITY__RELEASE"
                    ]
                    replacement["environment"] = environment
                if name == "api":
                    env = obj(replacement.get("environment", {}))
                    require(env.get(ASSETS) == after.env()[ASSETS], "api_map_not_injected")
                    env[ASSETS] = obj(original["environment"])[ASSETS]
                    replacement["environment"] = env
                else:
                    require(ASSETS not in obj(replacement.get("environment", {})), "map_scope")
            elif self.external is not None and name == self.external.service:
                self.external.check_render(original, replacement, before, after)
                replacement = original
            elif name != "migrate":
                # Unknown/AI services must never be part of a core redeploy.
                require(
                    obj(original.get("deploy", {})).get("replicas") == 0
                    and name == "external_delivery",
                    "non_core_service",
                )
                # A rendered disabled service inherits the global image even
                # though replicas remain zero. Normalize only that image field.
                if original.get("image") == before.env()[BACKEND]:
                    require(
                        replacement.get("image") == after.env()[BACKEND], "disabled_external_image"
                    )
                    replacement["image"] = original["image"]
                require(
                    not before.env().get("COMPOSE_PROFILES")
                    and not after.env().get("COMPOSE_PROFILES"),
                    "unknown_compose_profiles",
                )
            else:
                require(original.get("profiles") == ["ops"], "migration_profile")
                require(replacement.get("image") == after.env()[BACKEND], "migration_image")
                replacement["image"] = original["image"]
            require(replacement == original, "unexpected_rendered_change")
        require(obj(old["services"]).keys() >= ROLES, "missing_core_service")

    def put(self, before: Snapshot, after: Snapshot, phase: str) -> None:
        self.check_render(before, after)
        if self.external is not None:
            self.external.pre_write(phase)
        require(before.same(self.read()), "stale_stack_or_environment")
        self.io.checkpoint(phase + "_attempt")
        self.phase = phase + "_uncertain"
        try:
            self.io.request(
                f"/api/stacks/{self.target.stack_id}?endpointId={self.target.endpoint_id}",
                {
                    "StackFileContent": after.content,
                    "Env": after.stack["Env"],
                    "Prune": False,
                    "PullImage": False,
                },
                "PUT",
            )
        except Exception:
            raise RejectedError("write_uncertain_reconcile_before_retry") from None
        require(after.same(self.read()), "postwrite_stack_mismatch")
        self.phase = phase + "_accepted"
        self.io.checkpoint(self.phase)

    def verify(self, snapshot: Snapshot, images: dict[str, Image], baseline: Object) -> Object:
        if self.external is not None:
            require(
                images["backend"].sha in self.external.policy.core_compatible_sources,
                "external_core_runtime_source_not_reviewed",
            )
        evidence = self.io.evidence()
        require(evidence.get("schema") == SCHEMA, "schema_changed")
        require(
            evidence.get("ai") == baseline.get("ai") and bool(evidence.get("ai")),
            "ai_changed",
        )
        if self.external is None:
            require(evidence.get("external_delivery") == "stopped", "external_delivery_started")
        else:
            require(
                evidence.get("external_delivery") == self.external.observe(),
                "external_accepted_state_changed",
            )
        roles = obj(evidence.get("roles"))
        expected_roles = ROLES | ({self.external.service} if self.external else set())
        require(set(roles) == expected_roles, "runtime_roles")
        if self.external is not None:
            require(
                roles[self.external.service] == self.external.observe(), "external_runtime_role"
            )
        for role in ROLES:
            expected = images["frontend" if role == "frontend" else "backend"]
            actual = obj(roles[role])
            require(
                actual.get("reference") == expected.reference
                and actual.get("config") == expected.config
                and actual.get("revision") == expected.sha
                and actual.get("source") == SOURCE
                and actual.get("running") is True
                and actual.get("replicas") == 1,
                "runtime_identity",
            )
            if role not in {"api", "frontend"}:
                require(
                    actual.get("progress_after_start") is True,
                    "worker_progress_missing",
                )
        require(
            evidence.get("ready_path") == "/api/ready" and evidence.get("ready_status") == HTTP_OK,
            "application_readiness",
        )
        require(
            evidence.get("approved_releases") == array(snapshot.env()[ASSETS]),
            "api_asset_map",
        )
        require(
            evidence.get("served_release_id") == images["frontend"].sha
            and evidence.get("same_origin_contract") is True
            and evidence.get("authenticated_smoke") is True,
            "application_postcondition",
        )
        return evidence

    def promote(
        self,
        release: Object,
        baseline: Object,
        previous: dict[str, Image],
    ) -> Snapshot:
        require(not self.started, "attempt_already_started")
        self.started = True
        if self.external is not None:
            require(
                self.backend.sha in self.external.policy.core_compatible_sources,
                "external_core_source_not_reviewed",
            )
        before = self.read()
        require(
            baseline.get("schema") == SCHEMA
            and (
                baseline.get("external_delivery") == "stopped"
                if self.external is None
                else baseline.get("external_delivery") == self.external.observe()
            )
            and bool(baseline.get("ai")),
            "baseline",
        )
        require(
            before.env()[BACKEND] == previous["backend"].reference
            and before.env()[FRONTEND] == previous["frontend"].reference,
            "previous_images",
        )
        # Require proof from the verified digest's public map; parent binds bytes
        # to frontend smoke/config during evidence acquisition.
        require(release == self.io.frontend_release(self.frontend), "baked_asset_map")
        approved = merged_assets(before.env()[ASSETS], release, self.frontend.sha)
        staged = before.changed(
            {BACKEND: self.backend.reference, ASSETS: approved, RELEASE: self.backend.sha}
        )
        final = staged.changed({FRONTEND: self.frontend.reference})
        self.verify(before, previous, baseline)
        self.put(before, staged, "api_map")
        self.verify(
            staged,
            {"backend": self.backend, "frontend": previous["frontend"]},
            baseline,
        )
        self.put(staged, final, "frontend")
        self.verify(final, {"backend": self.backend, "frontend": self.frontend}, baseline)
        if self.external is not None and self.external.policy.upgrade_source == self.backend.sha:
            final = self.external.upgrade(self, final, self.backend)
            self.verify(final, {"backend": self.backend, "frontend": self.frontend}, baseline)
        self.phase = "verified"
        self.io.checkpoint(self.phase)
        return final

    def rollback(
        self,
        current: Snapshot,
        previous: dict[str, Image],
        baseline: Object,
        compatible_schema: str,
    ) -> Snapshot:
        if self.external is not None:
            require(
                previous["backend"].sha in self.external.policy.core_compatible_sources,
                "external_core_rollback_source_not_reviewed",
            )
        # Explicit reconciliation is required even after a failed promotion.
        require(compatible_schema == SCHEMA, "rollback_schema_compatibility")
        require(current.same(self.read()), "rollback_drift")
        safety = self.io.safety()
        require(safety.get("schema") == SCHEMA, "rollback_schema_changed")
        require(
            safety.get("ai") == baseline.get("ai")
            and (
                safety.get("external_delivery") == "stopped"
                if self.external is None
                else safety.get("external_delivery") == self.external.observe()
            ),
            "rollback_ownership_changed",
        )
        if self.external is not None and "external" in previous:
            current = self.external.upgrade(self, current, previous["external"])
        # Keep ALL approved maps so already-loaded newer clients retain support.
        ui = current.changed({FRONTEND: previous["frontend"].reference})
        self.put(current, ui, "rollback_frontend")
        core = ui.changed(
            {BACKEND: previous["backend"].reference, RELEASE: previous["backend"].sha}
        )
        self.put(ui, core, "rollback_backend")
        self.verify(core, previous, baseline)
        self.phase = "rollback_verified"
        self.io.checkpoint(self.phase)
        return core
