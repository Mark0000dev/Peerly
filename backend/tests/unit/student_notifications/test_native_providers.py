"""Actual JWT/signatures and controlled async HTTP only; all keys generated synthetically."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta, tzinfo
from importlib.metadata import PackageNotFoundError
from typing import ClassVar, Self
from urllib.parse import parse_qs
from uuid import uuid4

import httpx2 as httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa, utils

import studymate.infrastructure.student_notifications.providers as module
from studymate.domain.student_notifications.capabilities import Platform
from studymate.domain.student_notifications.delivery import Delivery, Kind, Outcome
from studymate.infrastructure.observability.logging import SafeJsonFormatter
from studymate.infrastructure.student_notifications.providers import (
    ApnsConfiguration,
    FcmConfiguration,
    ProviderKeyMaterial,
    ProviderSelection,
    PushProviders,
    selection_from_keys,
    unb64,
)

NOW = datetime(2026, 11, 14, 12, tzinfo=UTC)
LIFETIME_SECONDS = 300
ES_SIGNATURE_BYTES = 64
TOTAL_STREAM_CHUNKS = 3
HTTP_TIMEOUT = 2
APNS_TOKEN = "a1" * 32
FCM_DEVICE = "synthetic-device-token"


class Clock(datetime):
    at: ClassVar[datetime] = NOW

    @classmethod
    def now(cls, tz: tzinfo | None = None) -> Self:
        return cls.fromtimestamp(cls.at.timestamp(), tz)


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Clock, "at", NOW)
    monkeypatch.setattr(module, "datetime", Clock)


@pytest.fixture(scope="module")
def apns() -> ApnsConfiguration:
    return ApnsConfiguration(
        ec.generate_private_key(ec.SECP256R1()), "K" * 10, "T" * 10, "app.peerly.synthetic"
    )


@pytest.fixture(scope="module")
def fcm() -> FcmConfiguration:
    return FcmConfiguration(
        rsa.generate_private_key(public_exponent=65537, key_size=2048),
        "peerly-synthetic",
        "synthetic@peerly-synthetic.iam.gserviceaccount.com",
    )


@pytest.fixture
def delivery() -> Delivery:
    return Delivery(uuid4(), uuid4(), Kind.REQUEST, NOW + timedelta(days=1))


def mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    result: dict[str, object] = {}
    for key, entry in value.items():
        assert isinstance(key, str)
        result[key] = entry
    return result


def jwt(token: str) -> tuple[dict[str, object], dict[str, object], bytes, bytes]:
    header, claims, signature = token.split(".")
    return (
        mapping(json.loads(unb64(header))),
        mapping(json.loads(unb64(claims))),
        (header + "." + claims).encode(),
        unb64(signature),
    )


def pem(key: ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )


@pytest.mark.parametrize("sandbox", [False, True])
async def test_apns_fixed_host_es256_fresh_iat_headers_and_metadata_payload(
    apns: ApnsConfiguration, delivery: Delivery, sandbox: bool
) -> None:
    received: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        provider = PushProviders(client, apns=replace(apns, sandbox=sandbox))
        assert (
            await provider.send(delivery, Platform.IOS, APNS_TOKEN, None, None) == Outcome.ACCEPTED
        )
        Clock.at = NOW + timedelta(minutes=2)
        assert (
            await provider.send(delivery, Platform.IOS, APNS_TOKEN, None, None) == Outcome.ACCEPTED
        )
    for offset, request in zip((0, 120), received, strict=True):
        assert (
            str(request.url)
            == ("https://api.sandbox.push.apple.com" if sandbox else "https://api.push.apple.com")
            + "/3/device/"
            + APNS_TOKEN
        )
        assert request.method == "POST"
        assert request.headers["apns-topic"] == apns.topic
        assert request.headers["apns-id"] == str(delivery.id)
        assert request.headers["apns-push-type"] == "alert"
        assert request.headers["apns-expiration"] == "0"
        prefix, token = request.headers["authorization"].split(" ", 1)
        assert prefix == "bearer"
        header, claims, message, signature = jwt(token)
        assert header == {"alg": "ES256", "kid": apns.key_id}
        assert claims == {"iss": apns.team_id, "iat": int(NOW.timestamp()) + offset}
        assert len(signature) == ES_SIGNATURE_BYTES
        der = utils.encode_dss_signature(
            int.from_bytes(signature[:32], "big"), int.from_bytes(signature[32:], "big")
        )
        apns.key.public_key().verify(der, message, ec.ECDSA(hashes.SHA256()))
        assert json.loads(request.content) == {
            "aps": {"alert": {"title": "Peerly", "body": delivery.preview}}
        }
        assert str(delivery.recipient_id).encode() not in request.content


async def test_fcm_rs256_assertion_expiry_fresh_oauth_each_submission_and_metadata(
    fcm: FcmConfiguration, delivery: Delivery
) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "oauth2.googleapis.com":
            index = len([item for item in requests if item.url.host == "oauth2.googleapis.com"])
            return httpx.Response(
                200, json={"access_token": "synthetic-access-" + str(index), "expires_in": 1}
            )
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        provider = PushProviders(client, fcm=fcm)
        assert (
            await provider.send(delivery, Platform.ANDROID, FCM_DEVICE, None, None)
            == Outcome.ACCEPTED
        )
        Clock.at = NOW + timedelta(seconds=LIFETIME_SECONDS + 1)
        assert (
            await provider.send(delivery, Platform.ANDROID, FCM_DEVICE, None, None)
            == Outcome.ACCEPTED
        )
    oauth = [request for request in requests if request.url.host == "oauth2.googleapis.com"]
    messages = [request for request in requests if request.url.host == "fcm.googleapis.com"]
    for offset, request in zip((0, LIFETIME_SECONDS + 1), oauth, strict=True):
        assert str(request.url) == "https://oauth2.googleapis.com/token"
        form = parse_qs(request.content.decode())
        assert form["grant_type"] == ["urn:ietf:params:oauth:grant-type:jwt-bearer"]
        header, claims, signed, signature = jwt(form["assertion"][0])
        assert header == {"alg": "RS256", "typ": "JWT"}
        assert claims == {
            "iss": fcm.service_email,
            "scope": "https://www.googleapis.com/auth/firebase.messaging",
            "aud": "https://oauth2.googleapis.com/token",
            "iat": int(NOW.timestamp()) + offset,
            "exp": int(NOW.timestamp()) + offset + LIFETIME_SECONDS,
        }
        fcm.private_key.public_key().verify(signature, signed, padding.PKCS1v15(), hashes.SHA256())
    for index, request in enumerate(messages, 1):
        assert (
            str(request.url)
            == "https://fcm.googleapis.com/v1/projects/peerly-synthetic/messages:send"
        )
        assert request.headers["authorization"] == "Bearer synthetic-access-" + str(index)
        assert json.loads(request.content) == {
            "message": {
                "token": FCM_DEVICE,
                "notification": {"title": "Peerly", "body": delivery.preview},
            }
        }
        assert str(delivery.recipient_id).encode() not in request.content


@pytest.mark.parametrize(
    "reply",
    [
        (200, Outcome.ACCEPTED),
        (400, Outcome.REJECTED),
        (410, Outcome.REJECTED),
        (429, Outcome.RETRYABLE),
        (503, Outcome.UNKNOWN),
        (307, Outcome.UNKNOWN),
    ],
)
@pytest.mark.parametrize("platform", [Platform.IOS, Platform.ANDROID])
async def test_native_message_status_outcomes_and_no_redirects(
    apns: ApnsConfiguration,
    fcm: FcmConfiguration,
    delivery: Delivery,
    platform: Platform,
    reply: tuple[int, Outcome],
) -> None:
    status, expected = reply
    messages: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "synthetic-access"})
        messages.append(request)
        return httpx.Response(status, headers={"Location": "https://untrusted.invalid/redirect"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle), follow_redirects=True
    ) as client:
        result = await PushProviders(client, apns=apns, fcm=fcm).send(
            delivery, platform, APNS_TOKEN if platform == Platform.IOS else FCM_DEVICE, None, None
        )
    assert result == expected
    assert len(messages) == 1


@pytest.mark.parametrize("stage", ["oauth", "message"])
@pytest.mark.parametrize("failure", ["read", "write", "protocol", "timeout", "connect"])
async def test_oauth_nonacceptance_differs_from_ambiguous_message_submission(
    fcm: FcmConfiguration, delivery: Delivery, stage: str, failure: str
) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        oauth = request.url.host == "oauth2.googleapis.com"
        if oauth and stage != "oauth":
            return httpx.Response(200, json={"access_token": "synthetic-access"})
        if failure == "timeout":
            raise TimeoutError("synthetic provider failure")
        errors = {
            "read": httpx.ReadTimeout,
            "write": httpx.WriteError,
            "protocol": httpx.RemoteProtocolError,
            "connect": httpx.ConnectTimeout,
        }
        raise errors[failure]("synthetic provider failure", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        outcome = await PushProviders(client, fcm=fcm).send(
            delivery, Platform.ANDROID, FCM_DEVICE, None, None
        )
    assert outcome == (
        Outcome.RETRYABLE if stage == "oauth" or failure == "connect" else Outcome.UNKNOWN
    )
    assert len(requests) == (1 if stage == "oauth" else 2)


class Oversize(httpx.AsyncByteStream):
    def __init__(self) -> None:
        self.closed = False
        self.chunks = 0

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for _ in range(3):
            self.chunks += 1
            yield b"x" * 16384

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.parametrize(
    "case",
    [
        "unauthorized",
        "redirect",
        "invalid_json",
        "invalid_utf8",
        "not_object",
        "missing",
        "not_string",
        "empty",
        "too_long",
        "oversize",
    ],
)
async def test_bad_oauth_response_never_submits_message_and_closes_stream(
    fcm: FcmConfiguration, delivery: Delivery, case: str
) -> None:
    received: list[httpx.Request] = []
    stream = Oversize()

    def handle(request: httpx.Request) -> httpx.Response:
        received.append(request)
        assert request.url.host == "oauth2.googleapis.com"
        if case == "unauthorized":
            return httpx.Response(401)
        if case == "redirect":
            return httpx.Response(307, headers={"Location": "https://untrusted.invalid"})
        if case in ("invalid_json", "invalid_utf8"):
            return httpx.Response(200, content=b"not-json" if case == "invalid_json" else b"\xff")
        if case == "not_object":
            return httpx.Response(200, json=[])
        if case == "oversize":
            return httpx.Response(200, stream=stream)
        values: dict[str, object] = {
            "missing": {},
            "not_string": {"access_token": 1},
            "empty": {"access_token": ""},
            "too_long": {"access_token": "x" * 8193},
        }
        return httpx.Response(200, json=values[case])

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle), follow_redirects=True
    ) as client:
        assert (
            await PushProviders(client, fcm=fcm).send(
                delivery, Platform.ANDROID, FCM_DEVICE, None, None
            )
            == Outcome.RETRYABLE
        )
    assert len(received) == 1
    if case == "oversize":
        assert stream.closed
        assert stream.chunks < TOTAL_STREAM_CHUNKS


@pytest.mark.parametrize("platform", [Platform.WEB, Platform.IOS, Platform.ANDROID])
async def test_unconfigured_adapter_performs_no_http(
    delivery: Delivery, platform: Platform
) -> None:
    def never(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("Unconfigured provider must not issue HTTP")

    async with httpx.AsyncClient(transport=httpx.MockTransport(never)) as client:
        assert (
            await PushProviders(client).send(delivery, platform, APNS_TOKEN, None, None)
            == Outcome.REJECTED
        )


@pytest.mark.parametrize("token", ["", "invalid/slash", "a" * 513])
async def test_invalid_apns_endpoint_is_rejected_before_http(
    apns: ApnsConfiguration, delivery: Delivery, token: str
) -> None:
    def never(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("Invalid APNs token must not issue HTTP")

    async with httpx.AsyncClient(transport=httpx.MockTransport(never)) as client:
        assert (
            await PushProviders(client, apns=apns).send(delivery, Platform.IOS, token, None, None)
            == Outcome.REJECTED
        )


@pytest.mark.parametrize("stage", ["oauth", "message"])
async def test_native_cancellation_propagates_without_submission_retry(
    fcm: FcmConfiguration, delivery: Delivery, stage: str
) -> None:
    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url.host))
        if stage == "message" and request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "synthetic-access"})
        raise asyncio.CancelledError

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(asyncio.CancelledError):
            await PushProviders(client, fcm=fcm).send(
                delivery, Platform.ANDROID, FCM_DEVICE, None, None
            )
    assert calls == (
        ["oauth2.googleapis.com"]
        if stage == "oauth"
        else ["oauth2.googleapis.com", "fcm.googleapis.com"]
    )


@pytest.mark.parametrize(
    "case",
    [
        "apns_partial",
        "apns_rsa",
        "apns_curve",
        "apns_incomplete",
        "apns_identity",
        "fcm_partial",
        "fcm_ec",
        "fcm_project",
        "fcm_email",
    ],
)
def test_invalid_native_startup_material_is_rejected_without_clients(
    apns: ApnsConfiguration, fcm: FcmConfiguration, case: str
) -> None:
    value = ProviderKeyMaterial()
    if case == "apns_partial":
        value = replace(value, apns_key_id=apns.key_id)
    elif case.startswith("apns"):
        key = (
            pem(fcm.private_key)
            if case == "apns_rsa"
            else pem(ec.generate_private_key(ec.SECP384R1()))
            if case == "apns_curve"
            else pem(apns.key)
        )
        value = replace(
            value,
            apns_pem=key,
            apns_key_id="short" if case == "apns_identity" else apns.key_id,
            apns_team=apns.team_id,
            apns_topic=None if case == "apns_incomplete" else apns.topic,
        )
    elif case == "fcm_partial":
        value = replace(value, fcm_project=fcm.project)
    else:
        value = replace(
            value,
            fcm_pem=pem(apns.key) if case == "fcm_ec" else pem(fcm.private_key),
            fcm_project="BAD/PROJECT" if case == "fcm_project" else fcm.project,
            fcm_email="synthetic@example.invalid" if case == "fcm_email" else fcm.service_email,
        )
    with pytest.raises(ValueError, match=r"Partial|Complete|Invalid"):
        selection_from_keys(value)


@pytest.mark.parametrize("native", [False, True])
async def test_public_client_configuration_requires_http2_and_disables_proxy_redirect(
    monkeypatch: pytest.MonkeyPatch, apns: ApnsConfiguration, native: bool
) -> None:
    original = httpx.AsyncClient
    observed: list[bool] = []

    def controlled(
        *,
        http2: bool,
        timeout: httpx.Timeout,
        limits: httpx.Limits,
        follow_redirects: bool,
        trust_env: bool,
    ) -> httpx.AsyncClient:
        assert not trust_env
        assert not follow_redirects
        assert timeout.connect == timeout.read == timeout.write == timeout.pool == HTTP_TIMEOUT
        observed.append(http2)
        return original(
            transport=httpx.MockTransport(lambda _request: httpx.Response(200)),
            http2=http2,
            timeout=timeout,
            limits=limits,
            follow_redirects=follow_redirects,
            trust_env=trust_env,
        )

    monkeypatch.setenv("HTTPS_PROXY", "https://untrusted.invalid:9999")
    monkeypatch.setattr(httpx, "AsyncClient", controlled)
    selected = ProviderSelection(apns=apns if native else None)
    async with selected.client() as client:
        assert selected.adapters(client).apns == (apns if native else None)
    assert observed == [native]
    monkeypatch.setattr(module, "http2_available", lambda: False)
    if native:
        with pytest.raises(ValueError, match="h2"):
            selected.client()


async def test_provider_private_payload_response_and_tokens_do_not_export_in_logs(
    caplog: pytest.LogCaptureFixture,
    apns: ApnsConfiguration,
    fcm: FcmConfiguration,
    delivery: Delivery,
) -> None:
    caplog.set_level(logging.INFO)

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "SYNTHETIC_ACCESS_SECRET"})
        return httpx.Response(503, content=b"PRIVATE_PROVIDER_RESPONSE_BODY")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        provider = PushProviders(client, apns=apns, fcm=fcm)
        assert (
            await provider.send(delivery, Platform.IOS, APNS_TOKEN, None, None) == Outcome.UNKNOWN
        )
        assert (
            await provider.send(delivery, Platform.ANDROID, FCM_DEVICE, None, None)
            == Outcome.UNKNOWN
        )
    exported = "\n".join(SafeJsonFormatter().format(record) for record in caplog.records)
    for private in (
        APNS_TOKEN,
        FCM_DEVICE,
        "SYNTHETIC_ACCESS_SECRET",
        "PRIVATE_PROVIDER_RESPONSE_BODY",
        str(delivery.recipient_id),
    ):
        assert private not in exported


@pytest.mark.parametrize("installed", ["4.4.1", "4.3.0", "missing"])
def test_actual_http2_dependency_guard_is_pinned_and_closed(
    monkeypatch: pytest.MonkeyPatch, installed: str
) -> None:
    def lookup(_name: str) -> str:
        if installed == "missing":
            raise PackageNotFoundError
        return installed

    monkeypatch.setattr(module, "version", lookup)
    assert module.http2_available() == (installed == "4.4.1")
