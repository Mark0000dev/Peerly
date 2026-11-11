import time
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import httpx2 as httpx
import pytest
from joserfc import jwt
from joserfc.jwk import RSAKey

import studymate.infrastructure.identity.google as google_adapter
from studymate.application.identity.google import (
    GoogleAuthorization,
    GoogleCode,
    GoogleRejectedError,
    GoogleUnavailableError,
)
from studymate.domain.membership import GOOGLE_ISSUER, GoogleIdentity
from studymate.infrastructure.identity.google import (
    AUTHORIZE_URL,
    DISCOVERY_URL,
    EXCHANGE_URL,
    JWKS_URL,
    MAX_PROVIDER_BODY,
    GoogleConfiguration,
    GoogleOidcProvider,
)

CONFIG = GoogleConfiguration(
    "client.example", "synthetic-client-secret", "https://app.test/api/v1/auth/google/callback"
)
AUTH = GoogleAuthorization("state-value", "nonce-value", "v" * 43)
CODE = GoogleCode("synthetic-authorization-code")


@pytest.fixture(scope="module")
def signing_key() -> RSAKey:
    return RSAKey.generate_key(2048, parameters={"kid": "key-1"})


def signed_token(key: RSAKey, changes: dict[str, object] | None = None) -> str:
    now = int(time.time())
    claims: dict[str, object] = {
        "iss": GOOGLE_ISSUER,
        "sub": "subject-123",
        "aud": CONFIG.client_id,
        "iat": now,
        "exp": now + 300,
        "nonce": AUTH.nonce,
        "email": "personal@gmail.com",
        "email_verified": True,
    }
    claims.update(changes or {})
    return jwt.encode({"alg": "RS256", "kid": key.kid}, claims, key)


class ProviderServer:
    def __init__(self, key: RSAKey) -> None:
        self.key = key
        self.token = signed_token(key)
        self.discovery: object = {
            "issuer": GOOGLE_ISSUER,
            "authorization_endpoint": AUTHORIZE_URL,
            "token_endpoint": EXCHANGE_URL,
            "jwks_uri": JWKS_URL,
        }
        self.keys: object = {"keys": [key.as_dict()]}
        self.token_payload: object | None = None
        self.exchange_status = 200
        self.cache_headers: dict[str, str] = {}
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if str(request.url) == DISCOVERY_URL:
            return httpx.Response(200, json=self.discovery, headers=self.cache_headers)
        if str(request.url) == JWKS_URL:
            return httpx.Response(200, json=self.keys, headers=self.cache_headers)
        assert str(request.url) == EXCHANGE_URL
        assert request.method == "POST"
        data = parse_qs(request.content.decode())
        assert data["code"] == [CODE.value]
        if data["code_verifier"] != [AUTH.verifier]:
            return httpx.Response(400, json={"error": "invalid_grant"})
        assert data["client_id"] == [CONFIG.client_id]
        assert data["client_secret"] == [CONFIG.client_secret]
        assert data["redirect_uri"] == [CONFIG.redirect_uri]
        assert data["grant_type"] == ["authorization_code"]
        return httpx.Response(
            self.exchange_status,
            json=self.token_payload
            if self.token_payload is not None
            else {
                "id_token": self.token,
                "access_token": "synthetic-access",
                "token_type": "Bearer",
            },
        )


async def test_start_uses_pkce_nonce_fixed_endpoint_and_minimal_scope() -> None:
    async with httpx.AsyncClient() as http:
        url = await GoogleOidcProvider(CONFIG, http).authorization_url(AUTH)
    assert url.startswith(AUTHORIZE_URL + "?")
    parameters = parse_qs(urlsplit(url).query)
    assert parameters["scope"] == ["openid email profile"]
    assert parameters["state"] == [AUTH.state]
    assert parameters["nonce"] == [AUTH.nonce]
    assert parameters["code_challenge_method"] == ["S256"]
    assert parameters["code_challenge"][0] != AUTH.verifier
    assert "access_type" not in parameters
    assert "hd" not in parameters


async def test_pkce_mismatch_is_rejected_by_controlled_token_endpoint(
    signing_key: RSAKey,
) -> None:
    server = ProviderServer(signing_key)
    async with httpx.AsyncClient(transport=httpx.MockTransport(server.handle)) as http:
        provider = GoogleOidcProvider(CONFIG, http)
        with pytest.raises(GoogleRejectedError):
            await provider.exchange(CODE, replace(AUTH, verifier="different-verifier"))


async def test_valid_personal_google_token_returns_only_subject_and_caches_keys(
    signing_key: RSAKey,
) -> None:
    server = ProviderServer(signing_key)
    async with httpx.AsyncClient(transport=httpx.MockTransport(server.handle)) as http:
        provider = GoogleOidcProvider(CONFIG, http)
        assert await provider.exchange(CODE, AUTH) == GoogleIdentity(GOOGLE_ISSUER, "subject-123")
        assert await provider.exchange(CODE, AUTH) == GoogleIdentity(GOOGLE_ISSUER, "subject-123")
    assert [str(request.url) for request in server.requests].count(JWKS_URL) == 1
    assert CONFIG.client_secret not in repr(CONFIG)
    assert CODE.value not in repr(CODE)
    assert AUTH.verifier not in repr(AUTH)


@pytest.mark.parametrize(
    "changes",
    [
        {"iss": "https://evil.example"},
        {"aud": "other-client"},
        {"nonce": "wrong-nonce"},
        {"exp": int(time.time()) - 30},
        {"azp": "other-client"},
        {"sub": 123},
        {"sub": ""},
        {"aud": ["other-client"], "azp": CONFIG.client_id},
    ],
)
async def test_signed_but_invalid_assertions_are_rejected(
    signing_key: RSAKey,
    changes: dict[str, object],
) -> None:
    server = ProviderServer(signing_key)
    server.token = signed_token(signing_key, changes)
    async with httpx.AsyncClient(transport=httpx.MockTransport(server.handle)) as http:
        with pytest.raises(GoogleRejectedError):
            await GoogleOidcProvider(CONFIG, http).exchange(CODE, AUTH)


async def test_wrong_signature_with_known_key_id_is_rejected(signing_key: RSAKey) -> None:
    server = ProviderServer(signing_key)
    kid = signing_key.kid
    assert kid is not None
    attacker = RSAKey.generate_key(2048, parameters={"kid": kid})
    server.token = signed_token(attacker)
    async with httpx.AsyncClient(transport=httpx.MockTransport(server.handle)) as http:
        with pytest.raises(GoogleRejectedError):
            await GoogleOidcProvider(CONFIG, http).exchange(CODE, AUTH)


async def test_key_rotation_refreshes_trusted_jwks_once(signing_key: RSAKey) -> None:
    server = ProviderServer(signing_key)
    async with httpx.AsyncClient(transport=httpx.MockTransport(server.handle)) as http:
        provider = GoogleOidcProvider(CONFIG, http)
        await provider.exchange(CODE, AUTH)
        rotated = RSAKey.generate_key(2048, parameters={"kid": "key-2"})
        server.token = signed_token(rotated)
        server.keys = {"keys": [rotated.as_dict()]}
        await provider.exchange(CODE, AUTH)
    assert [str(request.url) for request in server.requests if str(request.url) == JWKS_URL] == [
        JWKS_URL,
        JWKS_URL,
    ]


@pytest.mark.parametrize(
    "headers",
    [
        {"Cache-Control": "no-store"},
        {"Cache-Control": "no-cache"},
        {"Cache-Control": "max-age=0"},
        {"Cache-Control": "max-age=5", "Age": "6"},
        {"Cache-Control": "max-age=invalid"},
        {"Cache-Control": "max-age"},
        {"Cache-Control": "max-age=" + "9" * 20},
        {"Age": "invalid"},
    ],
)
async def test_provider_cache_prohibitions_require_refetch(
    signing_key: RSAKey, headers: dict[str, str]
) -> None:
    server = ProviderServer(signing_key)
    server.cache_headers = headers
    async with httpx.AsyncClient(transport=httpx.MockTransport(server.handle)) as http:
        provider = GoogleOidcProvider(CONFIG, http)
        await provider.exchange(CODE, AUTH)
        await provider.exchange(CODE, AUTH)
    assert [str(request.url) for request in server.requests if str(request.url) == JWKS_URL] == [
        JWKS_URL,
        JWKS_URL,
    ]


@pytest.mark.parametrize(
    ("headers", "fresh_after", "expired_after"),
    [
        ({"Cache-Control": 'public, max-age="60"', "Age": "50"}, 9, 11),
        ({"Cache-Control": "public, max-age=3600", "Age": "1200"}, 599, 601),
    ],
)
async def test_provider_remaining_freshness_and_local_cache_cap_are_respected(
    signing_key: RSAKey,
    monkeypatch: pytest.MonkeyPatch,
    headers: dict[str, str],
    fresh_after: int,
    expired_after: int,
) -> None:
    server = ProviderServer(signing_key)
    server.cache_headers = headers
    clock = [100.0]
    monkeypatch.setattr(google_adapter, "monotonic", lambda: clock[0])
    async with httpx.AsyncClient(transport=httpx.MockTransport(server.handle)) as http:
        provider = GoogleOidcProvider(CONFIG, http)
        await provider.exchange(CODE, AUTH)
        clock[0] += fresh_after
        await provider.exchange(CODE, AUTH)
        assert [str(request.url) for request in server.requests].count(JWKS_URL) == 1
        clock[0] += expired_after - fresh_after
        await provider.exchange(CODE, AUTH)
    assert [str(request.url) for request in server.requests if str(request.url) == JWKS_URL] == [
        JWKS_URL,
        JWKS_URL,
    ]


@pytest.mark.parametrize(
    "discovery", [[], {"issuer": GOOGLE_ISSUER, "jwks_uri": "https://evil.example"}]
)
async def test_discovery_cannot_redirect_provider_fetches(
    signing_key: RSAKey, discovery: object
) -> None:
    server = ProviderServer(signing_key)
    server.discovery = discovery
    async with httpx.AsyncClient(transport=httpx.MockTransport(server.handle)) as http:
        with pytest.raises(GoogleUnavailableError):
            await GoogleOidcProvider(CONFIG, http).exchange(CODE, AUTH)
    assert len(server.requests) == 1


@pytest.mark.parametrize(
    "payload", [[], {}, {"id_token": "x"}, {"id_token": "x", "access_token": 1}]
)
async def test_malformed_token_response_is_rejected(signing_key: RSAKey, payload: object) -> None:
    server = ProviderServer(signing_key)
    server.token_payload = payload
    async with httpx.AsyncClient(transport=httpx.MockTransport(server.handle)) as http:
        with pytest.raises(GoogleRejectedError):
            await GoogleOidcProvider(CONFIG, http).exchange(CODE, AUTH)


@pytest.mark.parametrize("status", [400, 401, 403])
async def test_denied_or_invalid_code_requires_fresh_login(
    signing_key: RSAKey, status: int
) -> None:
    server = ProviderServer(signing_key)
    server.exchange_status = status
    async with httpx.AsyncClient(transport=httpx.MockTransport(server.handle)) as http:
        with pytest.raises(GoogleRejectedError):
            await GoogleOidcProvider(CONFIG, http).exchange(CODE, AUTH)


@pytest.mark.parametrize("status", [429, 503])
async def test_provider_outage_has_safe_error(signing_key: RSAKey, status: int) -> None:
    server = ProviderServer(signing_key)
    server.exchange_status = status
    async with httpx.AsyncClient(transport=httpx.MockTransport(server.handle)) as http:
        with pytest.raises(GoogleUnavailableError):
            await GoogleOidcProvider(CONFIG, http).exchange(CODE, AUTH)


async def test_http_timeout_is_translated() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("controlled timeout", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as http:
        with pytest.raises(GoogleUnavailableError):
            await GoogleOidcProvider(CONFIG, http).exchange(CODE, AUTH)


@pytest.mark.parametrize("body", [b"not-json", b"x" * (MAX_PROVIDER_BODY + 1)])
async def test_invalid_or_unbounded_provider_metadata_is_rejected(body: bytes) -> None:
    def response(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as http:
        with pytest.raises(GoogleUnavailableError):
            await GoogleOidcProvider(CONFIG, http).exchange(CODE, AUTH)


async def test_invalid_jwks_is_safe_provider_failure(signing_key: RSAKey) -> None:
    server = ProviderServer(signing_key)
    server.keys = {"keys": []}
    async with httpx.AsyncClient(transport=httpx.MockTransport(server.handle)) as http:
        with pytest.raises(GoogleUnavailableError):
            await GoogleOidcProvider(CONFIG, http).exchange(CODE, AUTH)


async def test_legacy_google_issuer_is_validated_and_canonicalised(signing_key: RSAKey) -> None:
    server = ProviderServer(signing_key)
    server.token = signed_token(signing_key, {"iss": "accounts.google.com"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(server.handle)) as http:
        assert await GoogleOidcProvider(CONFIG, http).exchange(CODE, AUTH) == GoogleIdentity(
            GOOGLE_ISSUER, "subject-123"
        )
