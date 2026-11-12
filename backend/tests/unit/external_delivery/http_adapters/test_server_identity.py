import json
from dataclasses import replace
from http import HTTPStatus
from uuid import UUID

import httpx2 as httpx
import pytest
from pydantic import SecretStr, ValidationError
from tests.unit.external_delivery.http_adapters.fixtures import lease, umami

from studymate.bootstrap import _external_destination_configs
from studymate.config import ExternalDeliveryWorkerSettings, UmamiDeliveryConfiguration
from studymate.domain.external_delivery.delivery import FailureCode, ResultKind
from studymate.infrastructure.external_delivery.http_adapters import (
    ExternalHttpSender,
    UmamiConfig,
    target_fingerprint,
)
from studymate.infrastructure.external_delivery.http_adapters.projections import umami_payload
from studymate.infrastructure.external_delivery.http_adapters.transport import UMAMI_USER_AGENT


@pytest.mark.parametrize(
    "hostname",
    [
        "https://app.test",
        "app.test/path",
        "app.test:443",
        "app.test?x=1",
        "app.test#f",
        "u:p@app.test",
        "APP.test",
        "localhost",
        "127.0.0.1",
        "app.test.",
        "a_b.test",
        "a" * 64 + ".test",
        "a." + "b" * 63 + ".example.test.more.labels.more.labels",
    ],
)
def test_untrusted_or_noncanonical_application_hostnames_fail_closed(hostname: str) -> None:
    with pytest.raises(ValueError, match="canonical application DNS hostname"):
        replace(umami(), hostname=hostname)
    with pytest.raises(ValidationError):
        UmamiDeliveryConfiguration(
            revision=1,
            origin="https://analytics.example.test",
            website_id=UUID(int=1),
            hostname=hostname,
        )


def test_worker_requires_hostname_and_maps_it_without_changing_registered_target_identity() -> None:
    with pytest.raises(ValidationError):
        UmamiDeliveryConfiguration.model_validate(
            {"revision": 1, "origin": "https://analytics.example.test", "website_id": UUID(int=1)}
        )
    configuration = UmamiDeliveryConfiguration(
        revision=1,
        origin="https://analytics.example.test",
        website_id=UUID(int=1),
        hostname="peerly-staging.aleksei-orlov.dev",
    )
    settings = ExternalDeliveryWorkerSettings(
        _env_file=None,
        database_url=SecretStr("postgresql+asyncpg://test:synthetic@localhost/owned_test"),
        umami=configuration,
        telegram_support=None,
        observability=None,
    )
    actual = _external_destination_configs(settings)[0]
    assert isinstance(actual, UmamiConfig)
    assert actual.destination.sink.value == "umami"
    assert actual.hostname == configuration.hostname
    assert target_fingerprint(actual) == target_fingerprint(replace(actual, hostname=None))


async def test_metadata_only_configuration_cannot_send_without_an_application_hostname() -> None:
    configuration = replace(umami(), hostname=None)
    calls: list[httpx.Request] = []

    async def provider(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"beep": "boop"})

    async with httpx.MockTransport(provider) as transport:
        result = await ExternalHttpSender((configuration,), transport).send(lease())
    assert result.kind == ResultKind.PERMANENT
    assert result.failure == FailureCode.DESTINATION
    assert result.http_status is None
    assert not calls
    with pytest.raises(ValueError, match="explicit application hostname"):
        umami_payload(lease(), configuration)


async def test_truthful_relay_transport_still_rejects_real_bot_filtered_http200_shape() -> None:
    configuration, job = umami(), lease()
    requests: list[httpx.Request] = []

    async def provider(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"beep": "boop"})

    async with httpx.MockTransport(provider) as transport:
        result = await ExternalHttpSender((configuration,), transport).send(job)
    assert result.kind == ResultKind.PERMANENT
    assert result.failure == FailureCode.DESTINATION
    assert result.http_status == HTTPStatus.OK
    request = requests[0]
    assert request.headers["user-agent"] == UMAMI_USER_AGENT
    assert "automated service" in UMAMI_USER_AGENT
    assert "Mozilla" not in UMAMI_USER_AGENT
    body: object = json.loads(request.content)
    assert isinstance(body, dict)
    payload = body["payload"]
    assert isinstance(payload, dict)
    assert payload["hostname"] == configuration.hostname
    assert (payload["browser"], payload["os"], payload["device"]) == ("service", "server", "server")
    assert "userAgent" not in payload
    assert "ip" not in payload
    data = payload["data"]
    assert isinstance(data, dict)
    assert data["delivery_provenance"] == "automated_application_service"
    assert data["trust"] == "server_committed"
