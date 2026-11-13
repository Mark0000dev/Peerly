"""Private acceptance and live singleton checks for the existing external consumer.

This observation adapter never starts/stops a process or writes delivery data.
The coordinator supplies the accepted private container configuration; no runtime
observation can mint acceptance. No acceptance means the original stopped policy.
"""

from __future__ import annotations

import copy
import re
import shlex
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from deployment.staging.release.data import Object, RejectedError, obj, require, rows, text
from deployment.staging.release.external_probe import EXTERNAL_DATABASE
from deployment.staging.release.release import ROLES, SCHEMA

if TYPE_CHECKING:
    from deployment.staging.release.portainer import Portainer

STACK_ID = 4
MODULE = "studymate.external_delivery_worker"
POTENTIALLY_ACTIVE = frozenset({"running", "paused", "restarting"})
SINKS = frozenset({"umami", "telegram_support"})


def executor(container: Object) -> bool:
    """Check Docker summary commands conservatively; ambiguity must block."""
    command = text(container.get("Command", ""))
    try:
        return MODULE in shlex.split(command) or MODULE in command
    except ValueError:
        return MODULE in command


def executors(portainer: Portainer, containers: list[Object]) -> list[Object]:
    result: list[Object] = []
    for container in containers:
        if container.get("State") not in POTENTIALLY_ACTIVE:
            continue
        if executor(container):
            result.append(container)
            continue
        labels = obj(container.get("Labels", {}))
        if (
            labels.get("com.docker.compose.project") == "peerly-staging"
            and labels.get("com.docker.compose.service") in ROLES
        ):
            continue  # Core commands are checked separately by Runtime.evidence.
        config = obj(portainer.inspect(text(container["Id"]))["Config"])
        commands = rows(config.get("Cmd") or []) + rows(config.get("Entrypoint") or [])
        if any(MODULE in text(value) for value in commands):
            result.append(container)
    return result


@dataclass(frozen=True, slots=True, repr=False)
class AcceptedExternal:
    acceptance_id: str
    service: str
    container_id: str
    image_config: str
    started_at: str
    pid: int
    # Actual Docker Config/HostConfig are private; do not hash/export secret Env.
    config: Object = field(repr=False)
    host_config: Object = field(repr=False)
    destinations: tuple[Object, ...] = field(repr=False)

    @classmethod
    def parse(cls, value: Object) -> AcceptedExternal:
        require(
            set(value)
            == {
                "version",
                "stack_id",
                "endpoint_id",
                "project",
                "acceptance_id",
                "service",
                "container_id",
                "image_config",
                "started_at",
                "pid",
                "config",
                "host_config",
                "destinations",
            }
            and type(value["version"]) is int
            and value["version"] == 1
            and type(value["stack_id"]) is int
            and value["stack_id"] == STACK_ID
            and type(value["endpoint_id"]) is int
            and value["endpoint_id"] == 1
            and value["project"] == "peerly-staging",
            "external_acceptance_scope",
        )
        acceptance_id, service = text(value["acceptance_id"]), text(value["service"])
        cid, image = text(value["container_id"]), text(value["image_config"])
        require(
            re.fullmatch(r"[A-Za-z0-9_-]{1,80}", acceptance_id) is not None,
            "external_acceptance_id",
        )
        require(service == "external_delivery", "external_service")
        require(
            re.fullmatch(r"[a-f0-9]{64}", cid) is not None
            and re.fullmatch(r"sha256:[a-f0-9]{64}", image) is not None,
            "external_identity",
        )
        pid = value["pid"]
        if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
            raise RejectedError("external_pid")
        config, host = copy.deepcopy(obj(value["config"])), copy.deepcopy(obj(value["host_config"]))
        labels = obj(config.get("Labels"))
        require(
            labels.get("com.docker.compose.project") == "peerly-staging"
            and labels.get("com.docker.compose.service") == service,
            "external_acceptance_labels",
        )
        require(MODULE in [text(v) for v in rows(config.get("Cmd"))], "external_command")
        require(config.get("User") == "10001:10001", "external_root")
        destinations = tuple(copy.deepcopy(obj(v)) for v in rows(value["destinations"]))
        require(0 < len(destinations) <= len(SINKS), "external_destination_count")
        sinks: set[str] = set()
        for destination in destinations:
            require(
                set(destination) == {"sink", "revision", "fingerprint"},
                "external_destination_shape",
            )
            sink = text(destination["sink"])
            require(sink in SINKS and sink not in sinks, "external_destination_sink")
            sinks.add(sink)
            revision = destination["revision"]
            require(type(revision) is int and revision > 0, "external_destination_revision")
            require(
                re.fullmatch(r"[a-f0-9]{64}", text(destination["fingerprint"])) is not None,
                "external_destination_fingerprint",
            )
        return cls(
            acceptance_id,
            service,
            cid,
            image,
            text(value["started_at"]),
            pid,
            config,
            host,
            destinations,
        )

    def matches(self, actual: Object) -> None:
        state = obj(actual.get("State"))
        require(
            actual.get("Id") == self.container_id
            and actual.get("Image") == self.image_config
            and state.get("Running") is True
            and state.get("Paused") is False
            and state.get("Restarting") is False
            and state.get("StartedAt") == self.started_at
            and state.get("Pid") == self.pid,
            "external_accepted_runtime_changed",
        )
        require(
            actual.get("Config") == self.config and actual.get("HostConfig") == self.host_config,
            "external_private_configuration_changed",
        )


def observe(portainer: Portainer, accepted: AcceptedExternal | None) -> Object:
    """Inspect the whole endpoint, not only stack labels; never infer acceptance."""
    containers = portainer.containers()
    running = [c for c in containers if c.get("State") in POTENTIALLY_ACTIVE and executor(c)]
    if accepted is None:
        require(not running, "external_unaccepted_executor")
        require(not executors(portainer, containers), "external_unaccepted_executor")
        return {"state": "stopped"}
    require(
        len(running) == 1 and running[0].get("Id") == accepted.container_id,
        "external_endpoint_singleton",
    )
    # A wrongly labelled extra running container with the accepted role blocks too,
    # even if its summary command has been changed to hide the worker module.
    role = [
        c
        for c in containers
        if c.get("State") in POTENTIALLY_ACTIVE
        and obj(c.get("Labels", {})).get("com.docker.compose.project") == "peerly-staging"
        and obj(c.get("Labels", {})).get("com.docker.compose.service") == accepted.service
    ]
    require(
        len(role) == 1 and role[0].get("Id") == accepted.container_id, "external_role_singleton"
    )
    discovered = executors(portainer, containers)
    require(
        len(discovered) == 1 and discovered[0].get("Id") == accepted.container_id,
        "external_full_command_singleton",
    )
    actual = portainer.inspect(accepted.container_id)
    accepted.matches(actual)
    return {
        "state": "active",
        "acceptance_id": accepted.acceptance_id,
        "container_id": accepted.container_id,
        "config": accepted.image_config,
        "started_at": accepted.started_at,
        "pid": accepted.pid,
    }


def destinations(portainer: Portainer, accepted: AcceptedExternal, database_name: str) -> Object:
    """Read only existing destinations after exact physical ownership preflight.

    Return private registered bindings for subsequent phase equality checks; never
    mint acceptance from them or require whole mutable delivery-table equality.
    """
    observe(portainer, accepted)
    result = portainer.probe(accepted.container_id, EXTERNAL_DATABASE)
    require(
        result.get("database_name") == database_name
        and database_name not in {"", "postgres", "default_db", "template0", "template1"},
        "external_database_target",
    )
    require(result.get("heads") == [SCHEMA], "external_actual_schema_barrier")
    configured = [obj(v) for v in rows(result.get("configured"))]
    expected = sorted(accepted.destinations, key=lambda row: text(row["sink"]))
    require(configured == expected, "external_configured_destinations_changed")
    registered = [obj(v) for v in rows(result.get("registered"))]
    require(all(v in registered for v in expected), "external_destination_not_registered")
    observe(portainer, accepted)
    return {"configured": configured, "registered": registered}
