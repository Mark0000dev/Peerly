"""Synthetic wire checks establish fail-closed policy, never live acceptance."""

from __future__ import annotations

import copy

import httpx
import pytest
from deployment.staging.release.data import Object, RejectedError, obj
from deployment.staging.release.external import AcceptedExternal, observe
from deployment.staging.release.portainer import DOCKER, Portainer
from deployment.staging.release.transport import Http

EXPECTED_READS = 2
CID = "a" * 64
CONFIG: Object = {
    "Labels": {
        "com.docker.compose.project": "peerly-staging",
        "com.docker.compose.service": "external_delivery",
    },
    "Cmd": ["python", "-m", "studymate.external_delivery_worker"],
    "User": "10001:10001",
    "Env": ["DATABASE_URL=synthetic-not-credential"],
}


def receipt() -> Object:
    return {
        "version": 1,
        "stack_id": 4,
        "endpoint_id": 1,
        "project": "peerly-staging",
        "acceptance_id": "synthetic-acceptance",
        "service": "external_delivery",
        "container_id": CID,
        "image_config": "sha256:" + "b" * 64,
        "started_at": "synthetic-start",
        "pid": 234,
        "config": copy.deepcopy(CONFIG),
        "host_config": {"ReadonlyRootfs": True},
        "destinations": [{"sink": "umami", "revision": 1, "fingerprint": "c" * 64}],
    }


def actual() -> Object:
    return {
        "Id": CID,
        "Image": "sha256:" + "b" * 64,
        "State": {
            "Running": True,
            "Paused": False,
            "Restarting": False,
            "StartedAt": "synthetic-start",
            "Pid": 234,
        },
        "Config": copy.deepcopy(CONFIG),
        "HostConfig": {"ReadonlyRootfs": True},
    }


def summary() -> Object:
    return {
        "Id": CID,
        "State": "running",
        "Command": "python -m studymate.external_delivery_worker",
        "Labels": copy.deepcopy(CONFIG["Labels"]),
    }


def adapter(containers: list[Object], inspected: Object) -> tuple[Portainer, list[str]]:
    calls: list[str] = []

    def serve(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        calls.append(request.url.raw_path.decode())
        if request.url.path == DOCKER + "/containers/json":
            assert list(request.url.params.multi_items()) == [("all", "true")]
            return httpx.Response(200, json=containers)
        assert request.url.path == DOCKER + f"/containers/{CID}/json"
        return httpx.Response(200, json=inspected)

    return Portainer(
        Http(httpx.MockTransport(serve)), "https://synthetic.invalid", "synthetic"
    ), calls


def test_stopped_default_never_inspects_or_adopts() -> None:
    portainer, calls = adapter([], {})
    assert observe(portainer, None) == {"state": "stopped"}
    assert len(calls) == 1


def test_unaccepted_running_blocks() -> None:
    portainer, calls = adapter([summary()], actual())
    with pytest.raises(RejectedError, match="external_unaccepted_executor"):
        observe(portainer, None)
    assert len(calls) == 1


def test_accepted_observation_contains_no_private_configuration() -> None:
    accepted = AcceptedExternal.parse(receipt())
    portainer, calls = adapter([summary()], actual())
    result = observe(portainer, accepted)
    assert result["state"] == "active"
    assert "DATABASE_URL" not in str(result) + repr(accepted)
    assert len(calls) == EXPECTED_READS


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("pid", True),
        ("stack_id", True),
        ("endpoint_id", 2),
        ("project", "production"),
        ("container_id", "short"),
        ("destinations", []),
    ],
)
def test_invalid_acceptance_is_not_observation(field: str, value: object) -> None:
    record = receipt()
    record[field] = value
    with pytest.raises(RejectedError):
        AcceptedExternal.parse(record)


@pytest.mark.parametrize("mutation", ["pid", "paused", "env", "host", "image"])
def test_runtime_or_private_configuration_drift_blocks(mutation: str) -> None:
    inspected = actual()
    if mutation == "pid":
        obj(inspected["State"])["Pid"] = 235
    elif mutation == "paused":
        obj(inspected["State"])["Paused"] = True
    elif mutation == "env":
        obj(inspected["Config"])["Env"] = ["DATABASE_URL=different-synthetic"]
    elif mutation == "host":
        obj(inspected["HostConfig"])["ReadonlyRootfs"] = False
    else:
        inspected["Image"] = "sha256:" + "d" * 64
    portainer, _ = adapter([summary()], inspected)
    with pytest.raises(RejectedError):
        observe(portainer, AcceptedExternal.parse(receipt()))


def test_endpoint_executor_outside_project_blocks() -> None:
    other = summary()
    other["Id"] = "d" * 64
    other["Labels"] = {}
    portainer, calls = adapter([summary(), other], actual())
    with pytest.raises(RejectedError, match="external_endpoint_singleton"):
        observe(portainer, AcceptedExternal.parse(receipt()))
    assert len(calls) == 1


def test_same_role_hidden_command_blocks() -> None:
    other = summary()
    other["Id"] = "d" * 64
    other["Command"] = "sleep infinity"
    portainer, _ = adapter([summary(), other], actual())
    with pytest.raises(RejectedError, match="external_role_singleton"):
        observe(portainer, AcceptedExternal.parse(receipt()))


@pytest.mark.parametrize("accepted", [False, True])
def test_hidden_outside_project_command_is_inspected_and_blocks(accepted: bool) -> None:
    hidden = {"Id": "d" * 64, "State": "running", "Labels": {}, "Command": "launch.sh"}

    def serve(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        if request.url.path == DOCKER + "/containers/json":
            return httpx.Response(200, json=([summary()] if accepted else []) + [hidden])
        assert request.url.path == DOCKER + "/containers/" + "d" * 64 + "/json"
        return httpx.Response(
            200, json={"Config": {"Cmd": ["python", "-m", "studymate.external_delivery_worker"]}}
        )

    portainer = Portainer(
        Http(httpx.MockTransport(serve)), "https://synthetic.invalid", "synthetic"
    )
    with pytest.raises(
        RejectedError, match=r"external_(?:full_command_singleton|unaccepted_executor)"
    ):
        observe(portainer, AcceptedExternal.parse(receipt()) if accepted else None)


@pytest.mark.parametrize("state", ["paused", "restarting"])
def test_paused_or_restarting_unaccepted_emitter_is_not_stopped(state: str) -> None:
    candidate = summary()
    candidate["State"] = state
    portainer, _ = adapter([candidate], actual())
    with pytest.raises(RejectedError, match="external_unaccepted_executor"):
        observe(portainer, None)
