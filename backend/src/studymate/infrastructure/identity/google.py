"""Google-only OIDC using Authlib OAuth/claims and maintained JOSE verification.

Provider-controlled links and JWT header URLs are never fetched. Tokens and
claims remain inside this boundary; only the validated issuer/subject escapes.
"""

import asyncio
from dataclasses import dataclass, field
from http import HTTPStatus
from time import monotonic
from typing import Literal

import httpx2 as httpx
from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.httpx_client import AsyncOAuth2Client
from authlib.oauth2.rfc6749.parameters import prepare_token_request
from authlib.oidc.core import CodeIDToken
from joserfc import jwt
from joserfc.errors import InvalidKeyIdError, JoseError
from joserfc.jwk import KeySet, RSAKey
from pydantic import BaseModel, ConfigDict, Field

from studymate.application.identity.google import (
    GoogleAuthorization,
    GoogleCode,
    GoogleRejectedError,
    GoogleUnavailableError,
)
from studymate.domain.membership import GOOGLE_ISSUER, GoogleIdentity

DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"
AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
EXCHANGE_URL = "https://oauth2.googleapis.com/token"
JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
MAX_PROVIDER_BODY = 65536
CACHE_SECONDS = 600
MAX_CACHE_SECONDS_DIGITS = 10
_CLIENT_AUTH_METHOD = "client_secret_post"


def _cache_lifetime(headers: httpx.Headers) -> int:
    """Conservatively cap provider freshness; invalid directives disable reuse."""
    age = headers.get("age", "0")
    if not age.isascii() or not age.isdecimal() or len(age) > MAX_CACHE_SECONDS_DIGITS:
        return 0
    lifetime = CACHE_SECONDS
    for directive in headers.get("cache-control", "").lower().split(","):
        name, separator, value = directive.strip().partition("=")
        if name in {"no-cache", "no-store"}:
            return 0
        if name == "max-age":
            value = value.strip().strip('"')
            if (
                not separator
                or not value.isascii()
                or not value.isdecimal()
                or len(value) > MAX_CACHE_SECONDS_DIGITS
            ):
                return 0
            lifetime = min(lifetime, max(0, int(value) - int(age)))
    return lifetime


class ProviderRsaKey(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    kty: Literal["RSA"]
    n: str
    e: str
    kid: str
    alg: Literal["RS256"] = "RS256"
    use: Literal["sig"] = "sig"


class ProviderKeySet(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    keys: tuple[ProviderRsaKey, ...] = Field(min_length=1, max_length=16)


@dataclass(frozen=True, slots=True)
class GoogleConfiguration:
    client_id: str
    client_secret: str = field(repr=False)
    redirect_uri: str


class GoogleOidcProvider:
    def __init__(self, configuration: GoogleConfiguration, http: httpx.AsyncClient) -> None:
        self.configuration = configuration
        self.http = http
        self._keys: KeySet | None = None
        self._valid_until = 0.0
        self._cache_lock = asyncio.Lock()

    def _oauth_client(self) -> AsyncOAuth2Client:
        return AsyncOAuth2Client(
            client_id=self.configuration.client_id,
            client_secret=self.configuration.client_secret,
            redirect_uri=self.configuration.redirect_uri,
            scope="openid email profile",
            code_challenge_method="S256",
            token_endpoint_auth_method=_CLIENT_AUTH_METHOD,
            timeout=5.0,
            follow_redirects=False,
        )

    async def authorization_url(self, authorization: GoogleAuthorization) -> str:
        async with self._oauth_client() as oauth:
            url, _ = oauth.create_authorization_url(
                AUTHORIZE_URL,
                state=authorization.state,
                nonce=authorization.nonce,
                code_verifier=authorization.verifier,
            )
            return url

    async def _json(self, url: str) -> tuple[dict[str, object], float]:
        async with self.http.stream("GET", url) as response:
            response.raise_for_status()
            valid_until = monotonic() + _cache_lifetime(response.headers)
            content = bytearray()
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content) > MAX_PROVIDER_BODY:
                    raise GoogleUnavailableError
            try:
                data: object = httpx.Response(200, content=bytes(content)).json()
            except ValueError as error:
                raise GoogleUnavailableError from error
        if not isinstance(data, dict):
            raise GoogleUnavailableError
        # A provider object is untrusted until its fields are validated below.
        return {str(key): value for key, value in data.items()}, valid_until

    async def _load_keys(self, *, force: bool = False) -> KeySet:
        async with self._cache_lock:
            if not force and self._keys is not None and monotonic() < self._valid_until:
                return self._keys
            metadata, metadata_until = await self._json(DISCOVERY_URL)
            expected = {
                "issuer": GOOGLE_ISSUER,
                "authorization_endpoint": AUTHORIZE_URL,
                "token_endpoint": EXCHANGE_URL,
                "jwks_uri": JWKS_URL,
            }
            if any(metadata.get(key) != value for key, value in expected.items()):
                raise GoogleUnavailableError
            keys, keys_until = await self._json(JWKS_URL)
            try:
                parsed = ProviderKeySet.model_validate(keys)
                self._keys = KeySet(
                    [
                        RSAKey.import_key(
                            {
                                "kty": key.kty,
                                "n": key.n,
                                "e": key.e,
                                "kid": key.kid,
                                "alg": key.alg,
                                "use": key.use,
                            }
                        )
                        for key in parsed.keys
                    ]
                )
            except (ValueError, JoseError) as error:
                raise GoogleUnavailableError from error
            self._valid_until = min(metadata_until, keys_until)
            return self._keys

    async def exchange(
        self, code: GoogleCode, authorization: GoogleAuthorization
    ) -> GoogleIdentity:
        try:
            keys = await self._load_keys()
            body = prepare_token_request(
                "authorization_code",
                code=code.value,
                redirect_uri=self.configuration.redirect_uri,
                code_verifier=authorization.verifier,
                client_id=self.configuration.client_id,
                client_secret=self.configuration.client_secret,
            )
            async with self.http.stream(
                "POST",
                EXCHANGE_URL,
                content=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ) as response:
                if response.status_code == HTTPStatus.TOO_MANY_REQUESTS:
                    raise GoogleUnavailableError
                if (
                    HTTPStatus.BAD_REQUEST
                    <= response.status_code
                    < HTTPStatus.INTERNAL_SERVER_ERROR
                ):
                    raise GoogleRejectedError
                response.raise_for_status()
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    raw.extend(chunk)
                    if len(raw) > MAX_PROVIDER_BODY:
                        raise GoogleUnavailableError
                token: object = httpx.Response(200, content=bytes(raw)).json()
            if not isinstance(token, dict):
                raise GoogleRejectedError
            id_token: object = token.get("id_token")
            access_token: object = token.get("access_token")
            if not isinstance(id_token, str) or not isinstance(access_token, str):
                raise GoogleRejectedError
            try:
                decoded = jwt.decode(id_token, keys, algorithms=["RS256"])
            except InvalidKeyIdError:
                keys = await self._load_keys(force=True)
                decoded = jwt.decode(id_token, keys, algorithms=["RS256"])
            claims = CodeIDToken(
                decoded.claims,
                decoded.header,
                options={
                    "iss": {"essential": True, "values": [GOOGLE_ISSUER, "accounts.google.com"]},
                    "aud": {"essential": True, "value": self.configuration.client_id},
                },
                params={
                    "nonce": authorization.nonce,
                    "client_id": self.configuration.client_id,
                    "access_token": access_token,
                },
            )
            claims.validate(leeway=0)
            subject: object = decoded.claims.get("sub")
            if not isinstance(subject, str):
                raise GoogleRejectedError
            return GoogleIdentity(GOOGLE_ISSUER, subject)
        except (httpx.HTTPError, OSError) as error:
            raise GoogleUnavailableError from error
        except (JoseError, OAuthError, ValueError, KeyError) as error:
            raise GoogleRejectedError from error
