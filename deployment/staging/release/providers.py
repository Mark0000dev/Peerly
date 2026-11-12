"""Real GitHub artifact and GHCR digest acquisition for this repository only."""

from __future__ import annotations

import base64
import io
import re
import zipfile
from dataclasses import dataclass
from http import HTTPStatus
from typing import TYPE_CHECKING
from urllib.parse import urlencode, urlsplit

from deployment.staging.release.data import Object, integer, load, obj, require, rows, text
from deployment.staging.release.provenance import artifact_binding, verify_image

if TYPE_CHECKING:
    from deployment.staging.release.release import Image
from deployment.staging.release.transport import Http, Request

REPO = "/repos/Mark0000dev/Peerly"
GITHUB = "https://api.github.com"
REGISTRY = "https://ghcr.io"
PAGE_SIZE = 100
MAX_ARCHIVE_MEMBERS = 32
RECEIPT_MARKER = "PEERLY_BACKEND_PUBLICATION_V1="
MAX_ARCHIVE_FILE = 1024 * 1024
REDIRECTS = {HTTPStatus.FOUND, HTTPStatus.TEMPORARY_REDIRECT}


@dataclass(frozen=True, slots=True)
class Package:
    image: Image
    proof: Object
    release: Object


class Github:
    def __init__(self, http: Http, token: str) -> None:
        self.http = http
        self.headers = (
            ("Authorization", "Bearer " + token),
            ("Accept", "application/vnd.github+json"),
            ("X-GitHub-Api-Version", "2022-11-28"),
        )

    def get(self, path: str) -> Object:
        require(path.startswith(REPO + "/"), "github_path")
        return self.http.document(Request(GITHUB + path, headers=self.headers))

    def source(self, sha: str) -> None:
        require(obj(self.get(REPO + "/branches/main")["commit"])["sha"] == sha, "main_moved")

    def completed(self, sha: str, workflow: str) -> Object:
        query = urlencode({"head_sha": sha, "branch": "main", "event": "push", "per_page": 100})
        listing = self.get(REPO + "/actions/workflows/" + workflow + "/runs?" + query)
        candidates = [
            obj(item)
            for item in rows(listing["workflow_runs"])
            if obj(item).get("head_sha") == sha
            and obj(item).get("event") == "push"
            and obj(item).get("status") == "completed"
            and obj(item).get("conclusion") == "success"
        ]
        require(len(candidates) == 1, "quality_run_missing_or_ambiguous")
        run_id = integer(candidates[0]["id"])
        return self.get(REPO + f"/actions/runs/{run_id}")

    def artifact(self, run: Object, name: str) -> dict[str, bytes]:
        run_id = integer(run["id"])
        listing = self.get(REPO + f"/actions/runs/{run_id}/artifacts?per_page=100")
        require(integer(listing["total_count"]) <= PAGE_SIZE, "artifact_pagination")
        matches = [obj(a) for a in rows(listing["artifacts"]) if obj(a).get("name") == name]
        require(len(matches) == 1, "artifact_missing_or_ambiguous")
        artifact = matches[0]
        artifact_binding(run, artifact, run_id, integer(run["run_attempt"]), name)
        artifact_id = integer(artifact["id"])
        response = self.http.send(
            Request(GITHUB + REPO + f"/actions/artifacts/{artifact_id}/zip", headers=self.headers)
        )
        require(response.status in REDIRECTS, "artifact_redirect")
        url = response.headers.get("location", "")
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        require(
            parsed.scheme == "https"
            and (host.endswith((".blob.core.windows.net", ".actions.githubusercontent.com")))
            and parsed.username is None,
            "artifact_download_origin",
        )
        # Signed URL gets NO GitHub Authorization; transport never follows redirects.
        archive = self.http.send(Request(url))
        require(archive.status == HTTPStatus.OK, "artifact_download")
        result: dict[str, bytes] = {}
        with zipfile.ZipFile(io.BytesIO(archive.body)) as zipped:
            require(len(zipped.infolist()) <= MAX_ARCHIVE_MEMBERS, "artifact_members")
            for info in zipped.infolist():
                require(
                    info.file_size <= MAX_ARCHIVE_FILE
                    and "/" not in info.filename
                    and "\\" not in info.filename
                    and info.filename not in result,
                    "artifact_member",
                )
                if info.filename in {
                    "published.json",
                    "observation-release.json",
                    "approved-public-releases.json",
                }:
                    result[info.filename] = zipped.read(info)
        require("published.json" in result, "publication_receipt_missing")
        return result

    def backend_receipt(self, run: Object) -> dict[str, bytes]:
        run_id, attempt = integer(run["id"]), integer(run["run_attempt"])
        listing = self.get(REPO + f"/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100")
        require(integer(listing["total_count"]) <= PAGE_SIZE, "job_pagination")
        matches = [
            obj(j) for j in rows(listing["jobs"]) if obj(j).get("name") == "Publish backend image"
        ]
        require(len(matches) == 1 and matches[0].get("conclusion") == "success", "publish_job")
        job = matches[0]
        steps = [
            obj(step)
            for step in rows(job["steps"])
            if obj(step).get("name") == "Record exact backend publication receipt"
        ]
        require(len(steps) == 1 and steps[0].get("conclusion") == "success", "publish_receipt_step")
        response = self.http.send(
            Request(
                GITHUB + REPO + f"/actions/jobs/{integer(job['id'])}/logs", headers=self.headers
            )
        )
        if response.status in REDIRECTS:
            url = response.headers.get("location", "")
            host = urlsplit(url).hostname or ""
            require(
                host.endswith((".blob.core.windows.net", ".actions.githubusercontent.com")),
                "job_log_origin",
            )
            response = self.http.send(Request(url))
        require(response.status == HTTPStatus.OK, "job_logs")
        return {"published.json": backend_log_receipt(response.body)}


def backend_log_receipt(body: bytes) -> bytes:
    # Anchored actual stdout line, not a printed shell/script source line.
    pattern: re.Pattern[bytes] = re.compile(
        rb"^[0-9TZ:.+-]+ " + RECEIPT_MARKER.encode() + rb"(\{[^\r\n]+\})$", re.MULTILINE
    )
    matches: list[bytes] = pattern.findall(body.replace(b"\r\n", b"\n"))
    require(len(matches) == 1, "backend_receipt_log_missing_or_ambiguous")
    load(matches[0])
    return matches[0]


class Registry:
    def __init__(self, http: Http, username: str, token: str) -> None:
        self.http, self.username, self.token = http, username, token

    def fetch(self, role: str, reference: str) -> tuple[bytes, bytes]:
        prefix = "ghcr.io/mark0000dev/peerly-" + role + "@"
        require(
            role in {"backend", "frontend"} and reference.startswith(prefix), "registry_repository"
        )
        digest = reference.removeprefix(prefix)
        from deployment.staging.release.validation import check_digest

        check_digest(digest)
        repository = "mark0000dev/peerly-" + role
        basic = base64.b64encode((self.username + ":" + self.token).encode()).decode()
        query = urlencode({"service": "ghcr.io", "scope": "repository:" + repository + ":pull"})
        auth = self.http.document(
            Request(REGISTRY + "/token?" + query, headers=(("Authorization", "Basic " + basic),))
        )
        headers = (
            ("Authorization", "Bearer " + text(auth["token"])),
            (
                "Accept",
                (
                    "application/vnd.oci.image.manifest.v1+json,"
                    " application/vnd.docker.distribution.manifest.v2+json"
                ),
            ),
        )
        manifest = self.http.send(
            Request(REGISTRY + "/v2/" + repository + "/manifests/" + digest, headers=headers)
        )
        require(manifest.status == HTTPStatus.OK, "registry_manifest")
        config_digest = text(obj(load(manifest.body)["config"])["digest"])
        check_digest(config_digest)
        config = self.http.send(
            Request(REGISTRY + "/v2/" + repository + "/blobs/" + config_digest, headers=headers)
        )
        if config.status in REDIRECTS:
            url = config.headers.get("location", "")
            require(
                urlsplit(url).hostname == "pkg-containers.githubusercontent.com",
                "registry_blob_origin",
            )
            config = self.http.send(Request(url))
        require(config.status == HTTPStatus.OK, "registry_config")
        return manifest.body, config.body

    def package(self, github: Github, role: str, sha: str) -> Package:
        workflow = "backend.yml" if role == "backend" else "frontend-image.yml"
        run = github.completed(sha, workflow)
        name = f"{role}-image-{sha}-{integer(run['run_attempt'])}"
        artifacts = github.backend_receipt(run) if role == "backend" else github.artifact(run, name)
        published = load(artifacts["published.json"])
        manifest, config = self.fetch(role, text(published["image"]))
        image = verify_image(
            (role, sha), run, published, manifest_bytes=manifest, config_bytes=config
        )
        proof: Object = {
            "run": run,
            "published": published,
            "labels": obj(obj(load(config)["config"])["Labels"]),
        }
        release = load(artifacts["observation-release.json"]) if role == "frontend" else {}
        return Package(image, proof, release)
