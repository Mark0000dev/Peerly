"""Preserve accepted active delivery, or upgrade only that owned singleton.

Same caller-held stack4 flock and full-stack CAS as the core promotion. A scoped
SIGTERM is followed by bounded observation, never SIGKILL/delete/queue cleanup.
Failures retain the caller's unresolved marker and private transition evidence.
"""

from __future__ import annotations

import base64
import copy
import os
import re
import time
from dataclasses import asdict, replace
from http import HTTPStatus
from typing import TYPE_CHECKING

from deployment.staging.release.data import Object, obj, require, rows, text
from deployment.staging.release.external import AcceptedExternal, destinations, executors, observe
from deployment.staging.release.external_metrics import progressed, sample
from deployment.staging.release.external_policy import (
    ExternalPolicy,
    read_private,
    save_private,
    sync,
)
from deployment.staging.release.external_probe import EXTERNAL_REGISTRY
from deployment.staging.release.release import BACKEND, ORIGIN, SCHEMA, SOURCE, Image, Snapshot
from deployment.staging.release.transport import Request

if TYPE_CHECKING:
    from pathlib import Path

    from deployment.staging.release.release import Promotion
    from deployment.staging.release.runtime import Runtime

EXTERNAL_IMAGE = "EXTERNAL_DELIVERY_IMAGE"
EXTERNAL_RELEASE = "EXTERNAL_DELIVERY_RELEASE"
GRACE_SECONDS = 45
CONVERGENCE_SECONDS = 180
POLL_SECONDS = 1
HOSTNAME_LENGTH = 12


class ExternalLifecycle:
    def __init__(self, runtime: Runtime, policy: ExternalPolicy) -> None:
        self.runtime, self.policy = runtime, policy
        self.accepted = policy.accepted
        self.directory = runtime.journal.path.parent
        self.planned: Image | None = None
        self.transition_bindings: Object | None = None
        self.initial_bindings: Object | None = None
        lineage = self.directory.parent / "external-lineage.private.json"
        if lineage.exists():
            raw = read_private(lineage)
            require(
                raw.get("acceptance_id") == policy.accepted.acceptance_id,
                "external_lineage_acceptance_changed",
            )
            current = AcceptedExternal.parse(obj(raw["current"]))
            require(
                current.acceptance_id == policy.accepted.acceptance_id, "external_lineage_identity"
            )
            self.compatible(policy.accepted, current, self.image(current))
            self.accepted = current

    @property
    def service(self) -> str:
        return self.accepted.service

    def image(self, accepted: AcceptedExternal | None = None) -> Image:
        current = accepted or self.accepted
        labels = obj(current.config["Labels"])
        reference = text(current.config["Image"])
        sha = text(labels["org.opencontainers.image.revision"])
        require(
            re.fullmatch(r"ghcr\.io/mark0000dev/peerly-backend@sha256:[a-f0-9]{64}", reference)
            is not None
            and labels.get("org.opencontainers.image.source") == SOURCE
            and sha in self.policy.compatible_sources,
            "external_image_binding",
        )
        inspected = self.runtime.portainer.image(reference)
        local_labels = obj(obj(inspected["Config"])["Labels"])
        require(
            inspected.get("Id") == current.image_config
            and local_labels.get("org.opencontainers.image.source") == SOURCE
            and local_labels.get("org.opencontainers.image.revision") == sha,
            "external_image_config",
        )
        image = Image("backend", sha, reference, current.image_config)
        self.policy.check_image(image)
        return image

    def known_snapshot(self, snapshot: Snapshot) -> None:
        image = self.image()
        require(not snapshot.env().get("COMPOSE_PROFILES"), "external_unknown_profiles")
        require(
            snapshot.env().get(EXTERNAL_IMAGE) == image.reference
            and snapshot.env().get(EXTERNAL_RELEASE) == image.sha,
            "external_independent_pin",
        )
        service = obj(obj(self.runtime.render(snapshot)["services"])[self.service])
        expected = copy.deepcopy(self.policy.service_spec)
        expected["image"] = image.reference
        obj(expected["environment"])["OBSERVABILITY__RELEASE"] = image.sha
        require(service == expected, "external_accepted_source_changed")

    def bindings(self) -> Object:
        entries = [text(v) for v in rows(self.accepted.config["Env"])]
        environment = {v.partition("=")[0]: v.partition("=")[2] for v in entries}
        require(len(environment) == len(entries), "external_environment_duplicates")
        if any(v["sink"] == "umami" for v in self.accepted.destinations):
            require(
                environment.get("UMAMI__HOSTNAME") == ORIGIN.removeprefix("https://"),
                "external_umami_hostname_binding",
            )
        require(
            environment.get("DATABASE_URL")
            == self.runtime.snapshot().env().get("PEERLY_DATABASE_URL"),
            "external_database_url_binding",
        )
        for key, value in obj(self.policy.service_spec["environment"]).items():
            expected = self.image().sha if key == "OBSERVABILITY__RELEASE" else text(value)
            require(environment.get(key) == expected, "external_rendered_environment_binding")
        current = destinations(
            self.runtime.portainer, self.accepted, self.runtime.inputs.database_name
        )
        if self.initial_bindings is None:
            self.initial_bindings = copy.deepcopy(current)
        require(current == self.initial_bindings, "external_registry_changed_across_phase")
        if self.transition_bindings is not None:
            require(
                current == self.transition_bindings, "external_registry_changed_across_transition"
            )
        return current

    def observe(self) -> Object:
        return observe(self.runtime.portainer, self.accepted)

    def metric(self, revision: str) -> bytes:
        basic = base64.b64encode(
            ("peerly-read:" + self.runtime.inputs.reader_password).encode()
        ).decode()
        response = self.runtime.http.send(
            Request(
                self.runtime.inputs.metrics_origin + "/peerly-observe/metrics/application",
                headers=(("Authorization", "Basic " + basic),),
            )
        )
        require(response.status == HTTPStatus.OK, "external_metrics_read_failed")
        sample(response.body, revision)
        return response.body

    def evidence(self, snapshot: Snapshot) -> Object:
        self.known_snapshot(snapshot)
        before = self.observe()
        bindings = self.bindings()
        image = self.image()
        first = sample(self.metric(image.sha), image.sha)
        end = time.monotonic() + CONVERGENCE_SECONDS
        while time.monotonic() < end:
            time.sleep(POLL_SECONDS)
            after = sample(self.metric(image.sha), image.sha)
            require(before == self.observe(), "external_changed_during_progress")
            if after.cycles > first.cycles:
                progressed(first, after)
                require(bindings == self.bindings(), "external_destination_registry_changed")
                return before
        raise TimeoutError("external_progress_deadline")

    def check_render(self, old: Object, new: Object, before: Snapshot, after: Snapshot) -> None:
        original = copy.deepcopy(old)
        replacement = copy.deepcopy(new)
        require(
            obj(original.get("deploy", {})).get("replicas") == 1
            and obj(replacement.get("deploy", {})).get("replicas") == 1,
            "external_activation_or_deactivation_forbidden",
        )
        if before.env().get(EXTERNAL_IMAGE) != after.env().get(EXTERNAL_IMAGE):
            require(self.planned is not None, "external_unplanned_image_change")
            if self.planned is None:
                raise ValueError("external_unplanned_image_change")
            require(
                replacement.get("image") == self.planned.reference
                and after.env().get(EXTERNAL_IMAGE) == self.planned.reference
                and after.env().get(EXTERNAL_RELEASE) == self.planned.sha
                and obj(replacement["environment"]).get("OBSERVABILITY__RELEASE")
                == self.planned.sha,
                "external_upgrade_render",
            )
            replacement["image"] = original["image"]
            obj(replacement["environment"])["OBSERVABILITY__RELEASE"] = obj(
                original["environment"]
            )["OBSERVABILITY__RELEASE"]
        require(original == replacement, "external_rendered_configuration_changed")

    def pre_write(self, phase: str) -> None:
        self.policy.check_current()
        if phase.startswith("external_"):
            self.exited(self.accepted)
            require(self.transition_bindings is not None, "external_transition_bindings_missing")
            if self.transition_bindings is None:
                raise ValueError("external_transition_bindings_missing")
            self.registry(self.transition_bindings)
        else:
            self.known_snapshot(self.runtime.snapshot())
            self.observe()
            self.bindings()

    def exit_state(self, accepted: AcceptedExternal) -> Object:
        actual = self.runtime.portainer.inspect(accepted.container_id)
        state = obj(actual["State"])
        require(
            actual.get("Id") == accepted.container_id
            and actual.get("Image") == accepted.image_config
            and actual.get("Config") == accepted.config
            and actual.get("HostConfig") == accepted.host_config
            and state.get("StartedAt") == accepted.started_at,
            "external_shutdown_identity_changed",
        )
        require(
            state.get("Running") is False
            and state.get("Pid") == 0
            and state.get("ExitCode") == 0
            and state.get("OOMKilled") is False
            and state.get("Error") == ""
            and bool(state.get("FinishedAt"))
            and state.get("Restarting") is False,
            "external_graceful_exit_unproven",
        )
        return {
            "container_id": accepted.container_id,
            "started_at": accepted.started_at,
            "finished_at": state["FinishedAt"],
            "exit_code": 0,
        }

    def exited(self, accepted: AcceptedExternal) -> Object:
        proof = self.exit_state(accepted)
        require(
            not executors(self.runtime.portainer, self.runtime.portainer.containers()),
            "external_executor_still_running",
        )
        return proof

    def registry(self, baseline: Object) -> None:
        candidates = [
            c
            for c in self.runtime.portainer.containers()
            if c.get("State") == "running"
            and obj(c.get("Labels", {})).get("com.docker.compose.project") == "peerly-staging"
            and obj(c.get("Labels", {})).get("com.docker.compose.service") == "api"
        ]
        require(len(candidates) == 1, "external_registry_probe_api_singleton")
        actual = self.runtime.portainer.inspect(text(candidates[0]["Id"]))
        snapshot = self.runtime.snapshot()
        local = self.runtime.portainer.image(snapshot.env()[BACKEND])
        labels = obj(obj(local["Config"])["Labels"])
        require(
            actual.get("Image") == local.get("Id")
            and labels.get("org.opencontainers.image.source") == SOURCE
            and labels.get("org.opencontainers.image.revision")
            in self.policy.core_compatible_sources,
            "external_registry_probe_core_image",
        )
        self.runtime.database_target(actual, snapshot)
        result = self.runtime.portainer.probe(text(actual["Id"]), EXTERNAL_REGISTRY)
        require(
            result.get("database_name") == self.runtime.inputs.database_name
            and result.get("heads") == [SCHEMA]
            and result.get("registered") == baseline.get("registered"),
            "external_registry_changed_before_start",
        )

    def compatible(self, old: AcceptedExternal, new: AcceptedExternal, image: Image) -> None:
        require(
            image.sha in self.policy.compatible_sources
            and image.config == new.image_config
            and new.config.get("Image") == image.reference
            and old.service == new.service
            and old.destinations == new.destinations
            and old.acceptance_id == new.acceptance_id
            and old.host_config == new.host_config,
            "external_recreation_scope",
        )
        expected = copy.deepcopy(old.config)
        actual = copy.deepcopy(new.config)
        expected["Image"] = image.reference
        if actual.get("Hostname") != expected.get("Hostname"):
            require(
                actual.get("Hostname") == new.container_id[:HOSTNAME_LENGTH]
                and expected.get("Hostname") == old.container_id[:HOSTNAME_LENGTH],
                "external_hostname_changed",
            )
            actual["Hostname"] = expected["Hostname"]
        env = [text(v) for v in rows(expected["Env"])]
        require(
            sum(v.startswith("OBSERVABILITY__RELEASE=") for v in env) == 1,
            "external_release_env_missing",
        )
        expected["Env"] = [
            "OBSERVABILITY__RELEASE=" + image.sha if v.startswith("OBSERVABILITY__RELEASE=") else v
            for v in env
        ]
        labels, new_labels = obj(expected["Labels"]), obj(actual["Labels"])
        baked = obj(obj(self.runtime.portainer.image(image.reference)["Config"])["Labels"])
        for key in tuple(labels):
            if key.startswith("org.opencontainers.image."):
                labels.pop(key)
        labels.update({k: v for k, v in baked.items() if k.startswith("org.opencontainers.image.")})
        for key in ("com.docker.compose.config-hash", "com.docker.compose.image"):
            if key in new_labels:
                value = text(new_labels[key])
                if key.endswith(".image"):
                    require(value == image.config, "external_compose_image_label")
                else:
                    require(
                        len(value) == len(image.config.removeprefix("sha256:"))
                        and all(v in "0123456789abcdef" for v in value),
                        "external_compose_config_hash",
                    )
                labels[key] = value
        require(expected == actual, "external_recreated_configuration_changed")

    def adopt(self, old: AcceptedExternal, image: Image) -> None:
        end = time.monotonic() + CONVERGENCE_SECONDS
        while time.monotonic() < end:
            candidates = executors(self.runtime.portainer, self.runtime.portainer.containers())
            if not candidates:
                time.sleep(POLL_SECONDS)
                continue
            require(len(candidates) == 1, "external_recreation_not_singleton")
            actual = self.runtime.portainer.inspect(text(candidates[0]["Id"]))
            state = obj(actual["State"])
            current = replace(
                old,
                container_id=text(actual["Id"]),
                image_config=text(actual["Image"]),
                started_at=text(state["StartedAt"]),
                pid=integer_pid(state["Pid"]),
                config=obj(actual["Config"]),
                host_config=obj(actual["HostConfig"]),
            )
            self.compatible(old, current, image)
            require(
                current.container_id != old.container_id or image == self.image(old),
                "external_upgrade_reused_old_container",
            )
            if current.container_id != old.container_id:
                old_rows = [
                    c
                    for c in self.runtime.portainer.containers()
                    if c.get("Id") == old.container_id
                ]
                require(
                    not any(c.get("State") == "running" for c in old_rows),
                    "external_old_executor_running",
                )
            self.accepted = current
            self.observe()
            return
        raise TimeoutError("external_recreation_deadline")

    def commit_lineage(self) -> None:
        value: Object = {
            "acceptance_id": self.policy.accepted.acceptance_id,
            "current": receipt(self.accepted),
        }
        target = self.directory.parent / "external-lineage.private.json"
        temporary = self.directory / "external-lineage.private.json"
        save_private(temporary, value)
        os.replace(temporary, target)
        sync(target.parent)

    def upgrade(self, promotion: Promotion, snapshot: Snapshot, image: Image) -> Snapshot:
        if self.image() == image:
            return snapshot
        self.policy.check_current()
        self.policy.check_image(image)
        local = self.runtime.portainer.image(image.reference)
        local_labels = obj(obj(local["Config"])["Labels"])
        require(
            local.get("Id") == image.config
            and local_labels.get("org.opencontainers.image.source") == SOURCE
            and local_labels.get("org.opencontainers.image.revision") == image.sha,
            "external_target_not_preloaded",
        )
        old_labels = obj(
            obj(self.runtime.portainer.image(self.image().reference)["Config"])["Labels"]
        )
        require(
            {k: v for k, v in local_labels.items() if not k.startswith("org.opencontainers.image.")}
            == {
                k: v for k, v in old_labels.items() if not k.startswith("org.opencontainers.image.")
            },
            "external_non_oci_image_labels_changed",
        )
        self.evidence(snapshot)
        old = self.accepted
        self.transition_bindings = self.bindings()
        save_private(
            self.directory / "external-before.private.json",
            {
                "accepted": receipt(old),
                "target": asdict(image),
                "bindings": self.transition_bindings,
                "snapshot": {"stack": snapshot.stack, "content": snapshot.content},
            },
        )
        self.runtime.inputs.check_source()
        self.policy.check_current()
        require(snapshot.same(promotion.read()), "external_pre_signal_stale_stack")
        self.runtime.checkpoint("external_term_attempt")
        self.runtime.portainer.terminate_owned(old.container_id)
        end = time.monotonic() + GRACE_SECONDS
        while time.monotonic() < end:
            if (
                obj(self.runtime.portainer.inspect(old.container_id)["State"]).get("Running")
                is False
            ):
                break
            time.sleep(POLL_SECONDS)
        require(time.monotonic() <= end, "external_graceful_exit_deadline")
        exit_proof = self.exited(old)
        save_private(self.directory / "external-exit.private.json", exit_proof)
        self.runtime.checkpoint("external_graceful_exit_verified")
        self.planned = image
        after = snapshot.changed({EXTERNAL_IMAGE: image.reference, EXTERNAL_RELEASE: image.sha})
        promotion.put(snapshot, after, "external_image")
        self.adopt(old, image)
        self.evidence(after)
        save_private(
            self.directory / "external-after.private.json", {"accepted": receipt(self.accepted)}
        )
        self.commit_lineage()
        self.runtime.checkpoint("external_verified")
        return after

    def reconcile(
        self, promotion: Promotion, snapshot: Snapshot, original: Path, *, rollback: bool
    ) -> Snapshot:
        record_path = original / "external-before.private.json"
        if not record_path.exists():
            return snapshot
        record = read_private(record_path)
        old = AcceptedExternal.parse(obj(record["accepted"]))
        target_raw = obj(record["target"])
        require(
            set(target_raw) == {"role", "sha", "reference", "config"},
            "external_recovery_image_shape",
        )
        target = Image(**{k: text(v) for k, v in target_raw.items()})
        require(
            target.role == "backend" and target.sha in self.policy.compatible_sources,
            "external_recovery_image",
        )
        self.compatible(self.policy.accepted, old, self.image(old))
        self.accepted = old
        self.transition_bindings = obj(record["bindings"])
        old_image = self.image(old)
        pin = snapshot.env().get(EXTERNAL_IMAGE)
        require(pin in {old_image.reference, target.reference}, "external_recovery_unknown_pin")
        containers = self.runtime.portainer.containers()
        old_running = any(
            c.get("Id") == old.container_id and c.get("State") == "running" for c in containers
        )
        if pin == old_image.reference and old_running:
            self.observe()
            return snapshot
        phases = (original / "journal").read_text().splitlines()
        require("external_term_attempt" in phases, "external_recovery_no_owned_stop_intent")
        exit_path = original / "external-exit.private.json"
        if exit_path.exists():
            exit_proof = read_private(exit_path)
            require(
                exit_proof.get("container_id") == old.container_id
                and exit_proof.get("started_at") == old.started_at
                and exit_proof.get("exit_code") == 0
                and bool(exit_proof.get("finished_at")),
                "external_recovery_exit_receipt",
            )
            if any(c.get("Id") == old.container_id for c in containers):
                require(exit_proof == self.exit_state(old), "external_recovery_exit_drift")
        else:
            require(pin == old_image.reference, "external_recovery_unproven_prior_exit")
            exit_proof = self.exited(old)
        self.registry(self.transition_bindings)
        if pin == target.reference:
            require(
                exit_path.exists() and "external_image_attempt" in phases,
                "external_recovery_unknown_write",
            )
            self.adopt(old, target)
            self.evidence(snapshot)
            self.commit_lineage()
            return snapshot
        return self.resume(promotion, snapshot, record, exit_proof, rollback)

    def resume(
        self,
        promotion: Promotion,
        snapshot: Snapshot,
        record: Object,
        exit_proof: Object,
        rollback: bool,
    ) -> Snapshot:
        old = self.accepted
        target_raw = obj(record["target"])
        target = Image(**{k: text(v) for k, v in target_raw.items()})
        old_image = self.image(old)
        self.policy.check_current()
        require(snapshot.same(promotion.read()), "external_recovery_stale_stack")
        if rollback:
            # This starts ONLY the exact formerly-active container whose owned
            # graceful shutdown was journalled. No bootstrap activation path.
            self.exited(old)
            self.runtime.checkpoint("external_restore_owned_attempt")
            self.runtime.portainer.start_owned_recovery(old.container_id)
            self.adopt(old, old_image)
            self.evidence(snapshot)
            self.commit_lineage()
            return snapshot
        save_private(self.directory / "external-before.private.json", record)
        save_private(self.directory / "external-exit.private.json", exit_proof)
        self.runtime.checkpoint("external_term_attempt")
        self.runtime.checkpoint("external_graceful_exit_verified")
        self.planned = target
        after = snapshot.changed({EXTERNAL_IMAGE: target.reference, EXTERNAL_RELEASE: target.sha})
        promotion.put(snapshot, after, "external_image")
        self.adopt(old, target)
        self.evidence(after)
        self.commit_lineage()
        self.runtime.checkpoint("external_verified")
        return after


def integer_pid(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError("external_pid")
    return value


def receipt(accepted: AcceptedExternal) -> Object:
    result: Object = asdict(accepted)
    result.update(version=1, stack_id=4, endpoint_id=1, project="peerly-staging")
    result["destinations"] = list(accepted.destinations)
    return result
