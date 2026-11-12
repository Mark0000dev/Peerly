import pytest
from deployment.staging.release.data import Object, RejectedError
from deployment.staging.release.publication import receipt
from deployment.staging.release.release import SOURCE


@pytest.fixture
def inspected() -> Object:
    return {
        "RepoDigests": ["ghcr.io/mark0000dev/peerly-backend@sha256:" + "b" * 64],
        "Id": "sha256:" + "c" * 64,
        "Config": {
            "Labels": {
                "org.opencontainers.image.source": SOURCE,
                "org.opencontainers.image.revision": "a" * 40,
            }
        },
    }


def test_publication_receipt(inspected: Object) -> None:
    data = receipt("a" * 40, [inspected])
    assert data["smoked_image_id"] == inspected["Id"]
    assert data["source_sha"] == "a" * 40


@pytest.mark.parametrize("delta", [{"RepoDigests": []}, {"Config": {"Labels": {}}}])
def test_missing_publication_identity(delta: Object, inspected: Object) -> None:
    with pytest.raises(RejectedError):
        receipt("a" * 40, [inspected | delta])
