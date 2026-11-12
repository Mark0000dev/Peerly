"""Verify registry bytes and exact existing CI publication receipts, offline."""

from __future__ import annotations

import hashlib

from deployment.staging.release.data import COMPOSE_TYPE, Object, load, obj, require
from deployment.staging.release.release import Image


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def verify_image(
    selection: tuple[str, str],
    run: Object,
    published: Object,
    *,
    manifest_bytes: bytes,
    config_bytes: bytes,
) -> Image:
    """Inputs are fetched by parent from the selected run and digest repository.

    OCI indexes are deliberately rejected. Select the actual linux/amd64 manifest
    and its immutable digest rather than trusting an index/config equivalence.
    """
    role, sha = selection
    manifest = load(manifest_bytes)
    config = load(config_bytes)
    require(
        manifest.get("schemaVersion") == COMPOSE_TYPE
        and manifest.get("mediaType")
        in {
            "application/vnd.oci.image.manifest.v1+json",
            "application/vnd.docker.distribution.manifest.v2+json",
        },
        "manifest_type",
    )
    require(
        obj(manifest.get("config")).get("digest") == digest(config_bytes),
        "registry_config_digest",
    )
    require(
        config.get("os") == "linux" and config.get("architecture") == "amd64",
        "runtime_platform",
    )
    img = Image(
        role,
        sha,
        "ghcr.io/mark0000dev/peerly-" + role + "@" + digest(manifest_bytes),
        digest(config_bytes),
    )
    img.validate(run, published, obj(obj(config.get("config")).get("Labels")))
    return img


def artifact_binding(
    run: Object,
    artifact: Object,
    run_id: int,
    attempt: int,
    expected_name: str,
) -> None:
    """Use metadata from GET /repos/Mark0000dev/Peerly/actions/runs/{id}/artifacts.

    Download only the exact returned archive_download_url on api.github.com;
    follow GitHub's authenticated redirect without forwarding authorization to
    another origin. No artifact cache or cross-run name search is permitted.
    """
    require(run.get("id") == run_id and run.get("run_attempt") == attempt, "run_attempt")
    require(
        artifact.get("name") == expected_name
        and artifact.get("expired") is False
        and obj(artifact.get("workflow_run")).get("id") == run_id
        and obj(artifact.get("workflow_run")).get("head_sha") == run.get("head_sha")
        and type(artifact.get("id")) is int,
        "artifact_run_binding",
    )
