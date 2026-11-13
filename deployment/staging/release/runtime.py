"""Real container, collector and same-origin application postconditions."""

from __future__ import annotations

import asyncio
import base64
import shlex
import time
from dataclasses import dataclass
from http import HTTPStatus
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlsplit

from deployment.staging.release.data import (
    Object,
    RejectedError,
    array,
    load,
    obj,
    require,
    rows,
    text,
)
from deployment.staging.release.external import observe as observe_external
from deployment.staging.release.external_lifecycle import ExternalLifecycle
from deployment.staging.release.metrics import METRICS, counters
from deployment.staging.release.native import render_native
from deployment.staging.release.probes import DATABASE, SAFETY_DATABASE
from deployment.staging.release.release import (
    ASSETS,
    BACKEND,
    FRONTEND,
    ORIGIN,
    RELEASE,
    ROLES,
    Image,
    Snapshot,
)
from deployment.staging.release.transport import Request

if TYPE_CHECKING:
    from collections.abc import Callable

    from deployment.staging.release.external_policy import ExternalPolicy
    from deployment.staging.release.journal import Journal
    from deployment.staging.release.portainer import Portainer
    from deployment.staging.release.providers import Package
    from deployment.staging.release.transport import Http

DEADLINE = 180
POLL = 5


@dataclass(frozen=True, slots=True)
class ObservationInputs:
    metrics_origin: str
    reader_password: str
    cookie: str
    account_id: str
    ai_id: str
    database_name: str
    check_source: Callable[[], None]
    external_policy: ExternalPolicy | None = None


class Runtime:
    def __init__(
        self,
        portainer: Portainer,
        http: Http,
        journal: Journal,
        packages: dict[str, Package],
        inputs: ObservationInputs,
    ) -> None:
        self.portainer, self.http, self.journal = portainer, http, journal
        self.packages, self.inputs = packages, inputs
        self.external = (
            ExternalLifecycle(self, inputs.external_policy) if inputs.external_policy else None
        )

    def request(self, path: str, data: Object | None = None, method: str | None = None) -> Object:
        if method == "PUT":
            self.inputs.check_source()
        return self.portainer.request(path, data, method)

    def checkpoint(self, phase: str) -> None:
        self.journal.checkpoint(phase)

    def render(self, snapshot: Snapshot) -> Object:
        return asyncio.run(render_native(snapshot))

    def frontend_release(self, image: Image) -> Object:
        require(image == self.packages["frontend"].image, "frontend_selection")
        return self.packages["frontend"].release

    def snapshot(self) -> Snapshot:
        stack = self.portainer.request("/api/stacks/4")
        content = self.portainer.request("/api/stacks/4/file")
        return Snapshot(stack, text(content["StackFileContent"]))

    def inventory(self) -> tuple[dict[str, Object], Object]:
        all_containers = self.portainer.containers()
        if self.external is not None:
            self.external.observe()
        else:
            observe_external(self.portainer, None)
        core: dict[str, Object] = {}
        for item in all_containers:
            command = text(item.get("Command", ""))
            running = item.get("State") == "running"
            require(
                not (running and "studymate.external_delivery_worker" in command)
                or self.external is not None,
                "external_delivery_running",
            )
            labels = obj(item.get("Labels", {}))
            if labels.get("com.docker.compose.project") == "peerly-staging" and running:
                role = text(labels.get("com.docker.compose.service"))
                if self.external is not None and role == self.external.service:
                    continue
                require(role in ROLES and role not in core, "core_role_count")
                core[role] = self.portainer.inspect(text(item["Id"]))
        require(set(core) == ROLES, "core_role_count")
        for role in METRICS:
            module = "studymate." + role + "_worker"
            matching = [
                c
                for c in all_containers
                if c.get("State") == "running" and module in shlex.split(text(c.get("Command", "")))
            ]
            require(
                len(matching) == 1 and matching[0]["Id"] == core[role]["Id"],
                "worker_not_endpoint_singleton",
            )
        ai = self.portainer.inspect(self.inputs.ai_id)
        require(obj(ai["State"]).get("Running") is True, "ai_not_running")
        # Existing canonical worker is launched by provision_bootstrap under a
        # holding init command, not necessarily Config.Cmd=studymate.ai_worker.
        # Do not exec inside AI or inspect its credential/receipt files.
        require(obj(ai["Config"]).get("User") == "10002:10002", "canonical_ai_user")
        return core, ai

    def settled(self, snapshot: Snapshot) -> tuple[dict[str, Object], Object]:
        expected = {
            r: self.portainer.image(snapshot.env()[FRONTEND if r == "frontend" else BACKEND])["Id"]
            for r in ROLES
        }
        end = time.monotonic() + DEADLINE
        while time.monotonic() < end:
            try:
                core, ai = self.inventory()
            except RejectedError as error:
                if str(error) != "core_role_count":
                    raise
            else:
                if all(core[r]["Image"] == expected[r] for r in ROLES):
                    return core, ai
            asyncio.run(asyncio.sleep(POLL))
        raise TimeoutError("container_convergence_deadline")

    def metric_sample(self, release: str) -> dict[str, float]:
        basic = base64.b64encode(("peerly-read:" + self.inputs.reader_password).encode()).decode()
        response = self.http.send(
            Request(
                self.inputs.metrics_origin + "/peerly-observe/metrics/application",
                headers=(("Authorization", "Basic " + basic),),
            )
        )
        require(response.status == HTTPStatus.OK, "collector_read_failed")
        return counters(response.body, release)

    def progressed(self, release: str, core: dict[str, Object]) -> None:
        first = self.metric_sample(release)
        end = time.monotonic() + DEADLINE
        while time.monotonic() < end:
            asyncio.run(asyncio.sleep(POLL))
            now = self.metric_sample(release)
            if all(now[r] > first[r] for r in METRICS):
                current, _ = self.inventory()
                require(
                    all(
                        current[r]["Id"] == core[r]["Id"]
                        and obj(current[r]["State"])["StartedAt"]
                        == obj(core[r]["State"])["StartedAt"]
                        for r in ROLES
                    ),
                    "runtime_changed_during_sample",
                )
                return
        raise TimeoutError("worker_progress_deadline")

    def web(self, cid: str) -> Object:
        response = self.http.send(Request(ORIGIN + "/assets/observation-release.json"))
        require(
            response.status == HTTPStatus.OK
            and response.headers.get("cache-control") == "no-cache"
            and "application/json" in response.headers.get("content-type", ""),
            "served_release_headers",
        )
        require(
            response.body == self.portainer.document(cid, "assets/observation-release.json"),
            "served_release_bytes",
        )
        release = load(response.body)
        require(release.get("origin") == ORIGIN, "served_origin")
        root = self.portainer.document(cid, "index.html")
        csr = self.portainer.document(cid, "index.csr.html")
        require(root != csr, "distinct_web_documents")
        for path, expected in [("/", root), ("/profile", csr), ("/index.csr.html", csr)]:
            response = self.http.send(Request(ORIGIN + path))
            require(
                response.status == HTTPStatus.OK
                and response.body == expected
                and "text/html" in response.headers.get("content-type", ""),
                "web_document",
            )
        for item in rows(release["assets"]):
            basename = text(obj(item)["basename"])
            require(
                "/" not in basename and "\\" not in basename and basename.endswith(".js"),
                "asset_basename",
            )
            response = self.http.send(Request(ORIGIN + "/" + basename))
            require(
                response.status == HTTPStatus.OK
                and "javascript" in response.headers.get("content-type", ""),
                "web_asset",
            )
        anonymous = self.http.send(Request(ORIGIN + "/api/v1/me"))
        require(anonymous.status == HTTPStatus.UNAUTHORIZED, "anonymous_identity")
        cookie = (("Cookie", "__Host-studymate_session=" + self.inputs.cookie),)
        identity = self.http.document(Request(ORIGIN + "/api/v1/me", headers=cookie))
        require(identity.get("account_id") == self.inputs.account_id, "smoke_identity")
        response = self.http.send(Request(ORIGIN + "/api/v1/me/profile", headers=cookie))
        require(
            response.status == HTTPStatus.OK
            and response.headers.get("cache-control") == "no-store",
            "authenticated_profile",
        )
        return release

    def database_target(self, container: Object, snapshot: Snapshot) -> None:
        expected = self.inputs.database_name
        require(
            bool(expected) and expected not in {"default_db", "postgres", "template0", "template1"},
            "database_target_input",
        )
        environment = {
            text(x).partition("=")[0]: text(x).partition("=")[2]
            for x in rows(obj(container["Config"])["Env"])
        }
        url = environment.get("DATABASE_URL", "")
        require(
            url == snapshot.env().get("PEERLY_DATABASE_URL")
            and unquote(urlsplit(url).path.removeprefix("/")) == expected,
            "database_target",
        )

    def safety(self) -> Object:
        # Rollback may repair a broken frontend/API. It requires live DB/AI
        # ownership, not a healthy current UI. Probe only an existing running
        # core backend with the exact declared digest and target DATABASE_URL.
        snapshot = self.snapshot()
        all_containers = self.portainer.containers()
        running = [c for c in all_containers if c.get("State") == "running"]
        if self.external is None:
            observe_external(self.portainer, None)
        require(
            self.external is not None
            or not any(
                "studymate.external_delivery_worker" in text(c.get("Command", "")) for c in running
            ),
            "external_delivery_running",
        )
        candidates = [
            c
            for c in running
            if obj(c.get("Labels", {})).get("com.docker.compose.project") == "peerly-staging"
            and obj(c.get("Labels", {})).get("com.docker.compose.service") in ROLES - {"frontend"}
        ]
        require(bool(candidates), "rollback_readonly_probe_unavailable")
        inspected = self.portainer.inspect(text(candidates[0]["Id"]))
        require(
            inspected["Image"] == self.portainer.image(snapshot.env()[BACKEND])["Id"],
            "rollback_probe_image",
        )
        self.database_target(inspected, snapshot)
        database = self.portainer.probe(text(inspected["Id"]), SAFETY_DATABASE)
        require(
            database.get("database_name") == self.inputs.database_name, "actual_database_target"
        )
        slot = obj(database["ai_slot"])
        require(slot.pop("fresh", False) is True, "ai_heartbeat_stale")
        heads = rows(database["heads"])
        require(len(heads) == 1, "schema_heads")
        ai = self.portainer.inspect(self.inputs.ai_id)
        require(obj(ai["State"]).get("Running") is True, "ai_not_running")
        identity: Object = {
            "container_id": ai["Id"],
            "config": ai["Image"],
            "started_at": obj(ai["State"])["StartedAt"],
            "pid": obj(ai["State"])["Pid"],
            "slot": slot,
        }
        external: object = "stopped"
        if self.external is not None:
            self.external.known_snapshot(snapshot)
            external = self.external.observe()
            self.external.bindings()
        return {"schema": heads[0], "ai": identity, "external_delivery": external}

    def evidence(self) -> Object:
        snapshot = self.snapshot()
        core, ai = self.settled(snapshot)
        require(snapshot.env().get("PEERLY_ENVIRONMENT") == "staging", "runtime_environment")
        self.progressed(snapshot.env()[RELEASE], core)
        self.database_target(core["api"], snapshot)
        database = self.portainer.probe(text(core["api"]["Id"]), DATABASE)
        require(
            database.get("database_name") == self.inputs.database_name, "actual_database_target"
        )
        slot = obj(database["ai_slot"])
        require(slot.pop("fresh", False) is True, "ai_heartbeat_stale")
        heads = rows(database["heads"])
        require(len(heads) == 1, "schema_heads")
        roles: Object = {}
        for role, container in core.items():
            reference = snapshot.env()[FRONTEND if role == "frontend" else BACKEND]
            inspected = self.portainer.image(reference)
            config = obj(container["Config"])
            labels = obj(config["Labels"])
            require(config.get("User") not in {"", "0", "root", None}, "runtime_root_user")
            require(container["Image"] == inspected["Id"], "container_config_binding")
            require(
                labels.get("com.docker.compose.project") == "peerly-staging"
                and labels.get("com.docker.compose.service") == role,
                "runtime_labels",
            )
            command = " ".join(text(x) for x in rows(config["Cmd"]))
            if role != "frontend":
                module = "server" if role == "api" else role + "_worker"
                require("studymate." + module in shlex.split(command), "runtime_command")
            roles[role] = {
                "reference": reference,
                "config": container["Image"],
                "revision": labels.get("org.opencontainers.image.revision"),
                "source": labels.get("org.opencontainers.image.source"),
                "running": obj(container["State"]).get("Running"),
                "replicas": 1,
                "progress_after_start": role in METRICS,
            }
        api_env = {
            text(x).split("=", 1)[0]: text(x).partition("=")[2]
            for x in rows(obj(core["api"]["Config"])["Env"])
        }
        require(array(api_env[ASSETS]) == database["approved_releases"], "actual_api_settings")
        served = self.web(text(core["frontend"]["Id"]))
        ready = self.http.send(Request(ORIGIN + "/api/ready"))
        ai_identity: Object = {
            "container_id": ai["Id"],
            "config": ai["Image"],
            "started_at": obj(ai["State"])["StartedAt"],
            "pid": obj(ai["State"])["Pid"],
            "slot": slot,
        }
        external: object = "stopped"
        if self.external is not None:
            external = self.external.evidence(snapshot)
            roles[self.external.service] = external
        return {
            "schema": heads[0],
            "ai": ai_identity,
            "external_delivery": external,
            "roles": roles,
            "ready_path": "/api/ready",
            "ready_status": ready.status,
            "approved_releases": database["approved_releases"],
            "served_release_id": served["releaseId"],
            "same_origin_contract": True,
            "authenticated_smoke": True,
        }
