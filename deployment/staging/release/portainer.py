"""Exact endpoint-1 Portainer operations. No auth discovery or arbitrary writes."""

from __future__ import annotations

import io
import re
import struct
import tarfile
from http import HTTPStatus
from urllib.parse import urlsplit

from deployment.staging.release.data import Object, RejectedError, load, obj, require, rows, text
from deployment.staging.release.transport import Http, Request, payload
from deployment.staging.release.validation import container_id

DOCKER = "/api/endpoints/1/docker"
FRAME_HEADER = 8
MAX_STATIC_DOCUMENT = 1024 * 1024


def demultiplex(raw: bytes) -> bytes:
    result = bytearray()
    while raw:
        require(len(raw) >= FRAME_HEADER, "docker_frame")
        stream, size = raw[0], struct.unpack(">I", raw[4:8])[0]
        require(stream == 1 and len(raw) >= FRAME_HEADER + size, "probe_stderr_or_frame")
        result.extend(raw[FRAME_HEADER : FRAME_HEADER + size])
        raw = raw[FRAME_HEADER + size :]
    return bytes(result)


class Portainer:
    def __init__(self, http: Http, origin: str, token: str) -> None:
        parsed = urlsplit(origin)
        require(
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and not parsed.path
            and not parsed.query
            and not parsed.fragment
            and parsed.username is None,
            "portainer_origin",
        )
        self.http, self.origin = http, origin
        self.headers = (("X-API-Key", token), ("Content-Type", "application/json"))

    def response(self, path: str, data: Object | None = None, method: str = "GET") -> bytes:
        allowed = path in {"/api/stacks/4", "/api/stacks/4/file"} or path.startswith(DOCKER + "/")
        if method == "PUT":
            allowed = path == "/api/stacks/4?endpointId=1" and data is not None
            if data is None:
                raise RejectedError("stack_payload")
            require(
                set(data) == {"StackFileContent", "Env", "Prune", "PullImage"}
                and data["Prune"] is False
                and data["PullImage"] is False,
                "stack_payload",
            )
        if method == "POST":
            allowed = (path.startswith(DOCKER + "/containers/") and path.endswith("/exec")) or (
                path.startswith(DOCKER + "/exec/") and path.endswith("/start")
            )
        if method == "POST" and data is None:
            allowed = (
                re.fullmatch(
                    re.escape(DOCKER) + r"/containers/[a-f0-9]{64}/(?:kill\?signal=SIGTERM|start)",
                    path,
                )
                is not None
            )
        require(allowed and method in {"GET", "PUT", "POST"}, "portainer_operation")
        response = self.http.send(
            Request(
                self.origin + path, method, self.headers, None if data is None else payload(data)
            )
        )
        require(
            response.status in {HTTPStatus.OK, HTTPStatus.CREATED, HTTPStatus.NO_CONTENT},
            "portainer_status",
        )
        return response.body

    def request(self, path: str, data: Object | None = None, method: str | None = None) -> Object:
        body = self.response(path, data, method or "GET")
        return load(body) if body else {}

    def containers(self) -> list[Object]:
        import json

        value: object = json.loads(self.response(DOCKER + "/containers/json?all=true"))
        return [obj(item) for item in rows(value)]

    def inspect(self, cid: str) -> Object:
        container_id(cid)
        return self.request(DOCKER + f"/containers/{cid}/json")

    def image(self, reference: str) -> Object:
        from urllib.parse import quote

        require(
            reference.startswith("ghcr.io/mark0000dev/peerly-") and "@sha256:" in reference,
            "preloaded_image",
        )
        return self.request(DOCKER + "/images/" + quote(reference, safe="") + "/json")

    def document(self, cid: str, name: str) -> bytes:
        from urllib.parse import urlencode

        container_id(cid)
        require(
            name in {"index.html", "index.csr.html", "assets/observation-release.json"},
            "static_document",
        )
        body = self.response(
            DOCKER
            + f"/containers/{cid}/archive?"
            + urlencode({"path": "/usr/share/nginx/html/" + name})
        )
        with tarfile.open(fileobj=io.BytesIO(body), mode="r:") as archive:
            members = archive.getmembers()
            require(
                len(members) == 1
                and members[0].isfile()
                and members[0].name == name.rsplit("/", 1)[-1]
                and members[0].size <= MAX_STATIC_DOCUMENT,
                "static_archive",
            )
            stream = archive.extractfile(members[0])
            require(stream is not None, "static_archive")
            if stream is None:
                raise RejectedError("static_archive")
            return stream.read()

    def probe(self, cid: str, script: str) -> Object:
        from deployment.staging.release.external_probe import EXTERNAL_DATABASE, EXTERNAL_REGISTRY
        from deployment.staging.release.probes import DATABASE, SAFETY_DATABASE

        require(
            script in {DATABASE, SAFETY_DATABASE, EXTERNAL_DATABASE, EXTERNAL_REGISTRY},
            "fixed_probe_only",
        )
        container_id(cid)
        created = self.request(
            DOCKER + f"/containers/{cid}/exec",
            {
                "AttachStdout": True,
                "AttachStderr": True,
                "Tty": False,
                "Cmd": ["python", "-c", script],
                "Privileged": False,
                "User": "10001:10001",
            },
            "POST",
        )
        eid = text(created["Id"])
        container_id(eid)
        raw = self.response(DOCKER + f"/exec/{eid}/start", {"Detach": False, "Tty": False}, "POST")
        state = self.request(DOCKER + f"/exec/{eid}/json")
        require(state.get("Running") is False and state.get("ExitCode") == 0, "probe_failed")
        return load(demultiplex(raw))

    def terminate_owned(self, cid: str) -> None:
        container_id(cid)
        self.response(DOCKER + f"/containers/{cid}/kill?signal=SIGTERM", method="POST")

    def start_owned_recovery(self, cid: str) -> None:
        container_id(cid)
        self.response(DOCKER + f"/containers/{cid}/start", method="POST")
