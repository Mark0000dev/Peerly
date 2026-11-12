import json

import pytest
from deployment.staging.release.data import Object, RejectedError, obj
from deployment.staging.release.provenance import artifact_binding, digest, verify_image
from deployment.staging.release.release import SOURCE, Image
from deployment.staging.release.tests.test_release import SELECTED_SHA, image, proof


@pytest.fixture
def registry() -> tuple[Object, bytes, bytes]:
    config = json.dumps(
        {
            "os": "linux",
            "architecture": "amd64",
            "config": {
                "Labels": {
                    "org.opencontainers.image.source": SOURCE,
                    "org.opencontainers.image.revision": SELECTED_SHA,
                }
            },
        }
    ).encode()
    manifest = json.dumps(
        {
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "config": {"digest": digest(config)},
        }
    ).encode()
    data = proof(image("backend", "b"))
    obj(data["published"]).update(
        image="ghcr.io/mark0000dev/peerly-backend@" + digest(manifest),
        digest=digest(manifest),
        smoked_image_id=digest(config),
    )
    return data, manifest, config


def verify(registry: tuple[Object, bytes, bytes]) -> Image:
    data, manifest, config = registry
    return verify_image(
        ("backend", SELECTED_SHA),
        obj(data["run"]),
        obj(data["published"]),
        manifest_bytes=manifest,
        config_bytes=config,
    )


def test_hash_binding(registry: tuple[Object, bytes, bytes]) -> None:
    assert verify(registry).config == digest(registry[2])


@pytest.mark.parametrize("changed", ["config", "manifest", "index"])
def test_registry_tampering(changed: str, registry: tuple[Object, bytes, bytes]) -> None:
    data, manifest, config = registry
    if changed == "config":
        config += b" "
    elif changed == "manifest":
        manifest += b" "
    else:
        manifest = b'{"schemaVersion":2,"mediaType":"application/vnd.oci.image.index.v1+json"}'
    with pytest.raises(RejectedError):
        verify((data, manifest, config))


@pytest.mark.parametrize("field", ["expired", "name", "workflow_run"])
def test_cross_run_artifacts(field: str, registry: tuple[Object, bytes, bytes]) -> None:
    run = obj(registry[0]["run"])
    artifact: Object = {
        "id": 20,
        "name": "backend-image-" + SELECTED_SHA + "-1",
        "expired": False,
        "workflow_run": {"id": 100, "head_sha": SELECTED_SHA},
    }
    name = str(artifact["name"])
    artifact_binding(run, artifact, 100, 1, name)
    artifact[field] = {
        "expired": True,
        "name": "other",
        "workflow_run": {"id": 101, "head_sha": SELECTED_SHA},
    }[field]
    with pytest.raises(RejectedError):
        artifact_binding(run, artifact, 100, 1, name)
