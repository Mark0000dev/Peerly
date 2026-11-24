"""Real async Web Push/APNs/FCM submission; never logs payloads/provider responses."""

import asyncio
import base64
import hashlib
import hmac
import json
import os
import struct
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http import HTTPStatus
from importlib.metadata import PackageNotFoundError, version
from urllib.parse import urlsplit

import httpx2 as httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa, utils
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from studymate.domain.student_notifications.capabilities import Platform
from studymate.domain.student_notifications.delivery import Delivery, Outcome

MAX_PAYLOAD = 1024
AUTH_BYTES = 16
OAUTH_BODY_MAX = 16384
OAUTH_TOKEN_MAX = 8192
APNS_TOKEN_MAX = 512


def b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def unb64(value: str) -> bytes:
    return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)


def ec_jwt(
    key: ec.EllipticCurvePrivateKey, header: dict[str, str], claims: dict[str, str | int]
) -> str:
    message = (
        b64(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + b64(json.dumps(claims, separators=(",", ":")).encode())
    )
    r, s = utils.decode_dss_signature(key.sign(message.encode(), ec.ECDSA(hashes.SHA256())))
    return message + "." + b64(r.to_bytes(32, "big") + s.to_bytes(32, "big"))


def encrypted_webpush(
    payload: bytes,
    public: bytes,
    auth: bytes,
    *,
    sender: ec.EllipticCurvePrivateKey | None = None,
    salt: bytes | None = None,
) -> bytes:
    """RFC8291 single aes128gcm record; optional key/salt exist for RFC vector tests only."""
    if len(payload) > MAX_PAYLOAD or len(auth) != AUTH_BYTES:
        raise ValueError("Bounded Web Push payload and auth secret required")
    sender = sender or ec.generate_private_key(ec.SECP256R1())
    salt = salt if salt is not None else os.urandom(16)
    if len(salt) != AUTH_BYTES:
        raise ValueError("Web Push salt must be sixteen bytes")
    server = sender.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public)
    shared = sender.exchange(ec.ECDH(), peer)
    prk_key = hmac.digest(auth, shared, hashlib.sha256)
    ikm = hmac.digest(prk_key, b"WebPush: info\0" + public + server + b"\x01", hashlib.sha256)
    prk = hmac.digest(salt, ikm, hashlib.sha256)
    cek = hmac.digest(prk, b"Content-Encoding: aes128gcm\0\x01", hashlib.sha256)[:16]
    nonce = hmac.digest(prk, b"Content-Encoding: nonce\0\x01", hashlib.sha256)[:12]
    encrypted = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)
    return salt + struct.pack("!IB", 4096, len(server)) + server + encrypted


@dataclass(frozen=True, slots=True)
class WebPushConfiguration:
    private_key: ec.EllipticCurvePrivateKey = field(repr=False)
    contact: str
    hosts: tuple[str, ...]

    @property
    def public_key(self) -> str:
        return b64(
            self.private_key.public_key().public_bytes(
                serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
            )
        )


@dataclass(frozen=True, slots=True)
class ApnsConfiguration:
    key: ec.EllipticCurvePrivateKey = field(repr=False)
    key_id: str
    team_id: str
    topic: str
    sandbox: bool = False


@dataclass(frozen=True, slots=True)
class FcmConfiguration:
    private_key: rsa.RSAPrivateKey = field(repr=False)
    project: str
    service_email: str = field(repr=False)


def http2_available() -> bool:
    try:
        return version("h2") == "4.4.1"
    except PackageNotFoundError:
        return False


def status_outcome(status: int) -> Outcome:
    if HTTPStatus.OK <= status < HTTPStatus.MULTIPLE_CHOICES:
        return Outcome.ACCEPTED
    # Only explicit rejection is safe to retry. Network/read timeout or5xx may be ambiguous.
    if status == HTTPStatus.TOO_MANY_REQUESTS:
        return Outcome.RETRYABLE
    if HTTPStatus.BAD_REQUEST <= status < HTTPStatus.INTERNAL_SERVER_ERROR:
        return Outcome.REJECTED
    return Outcome.UNKNOWN


@dataclass(frozen=True, slots=True)
class PushProviders:
    client: httpx.AsyncClient
    web: WebPushConfiguration | None = None
    apns: ApnsConfiguration | None = None
    fcm: FcmConfiguration | None = None

    async def _fcm_token(self, config: FcmConfiguration) -> str | None:
        now = int(datetime.now(UTC).timestamp())
        header = b64(b'{"alg":"RS256","typ":"JWT"}')
        claims = b64(
            json.dumps(
                {
                    "iss": config.service_email,
                    "scope": "https://www.googleapis.com/auth/firebase.messaging",
                    "aud": "https://oauth2.googleapis.com/token",
                    "iat": now,
                    "exp": now + 300,
                },
                separators=(",", ":"),
            ).encode()
        )
        data = header + "." + claims
        assertion = (
            data
            + "."
            + b64(config.private_key.sign(data.encode(), padding.PKCS1v15(), hashes.SHA256()))
        )
        async with self.client.stream(
            "POST",
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
            follow_redirects=False,
        ) as response:
            if response.status_code != HTTPStatus.OK:
                return None
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > OAUTH_BODY_MAX:
                    return None
            try:
                value: object = json.loads(body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return None
            token: object = value.get("access_token") if isinstance(value, dict) else None
            return token if isinstance(token, str) and 1 <= len(token) <= OAUTH_TOKEN_MAX else None

    async def send(
        self,
        delivery: Delivery,
        platform: Platform,
        endpoint: str,
        public: str | None,
        auth: str | None,
    ) -> Outcome:
        if platform == Platform.WEB:
            parsed = urlsplit(endpoint)
            if (
                self.web is None
                or parsed.scheme != "https"
                or parsed.hostname not in self.web.hosts
                or parsed.username
                or parsed.password
                or parsed.port not in (None, 443)
            ):
                return Outcome.REJECTED
        authorization_pending = platform == Platform.ANDROID and self.fcm is not None
        try:
            async with asyncio.timeout(2):
                if platform == Platform.ANDROID and self.fcm is not None:
                    access_token = await self._fcm_token(self.fcm)
                    if access_token is None:
                        return Outcome.RETRYABLE  # No message submission occurred.
                    authorization_pending = False
                    return await self._send_fcm(delivery, endpoint, self.fcm, access_token)
                return await self._send(delivery, platform, endpoint, public, auth)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
            return Outcome.RETRYABLE
        except (
            httpx.ReadError,
            httpx.ReadTimeout,
            httpx.WriteError,
            httpx.WriteTimeout,
            httpx.RemoteProtocolError,
            TimeoutError,
        ):
            # OAuth token exchange cannot deliver a student notification. Once the
            # message phase begins, read/write/protocol/deadline failures stay ambiguous.
            return Outcome.RETRYABLE if authorization_pending else Outcome.UNKNOWN

    async def _send(
        self,
        delivery: Delivery,
        platform: Platform,
        endpoint: str,
        public: str | None,
        auth: str | None,
    ) -> Outcome:
        now = int(datetime.now(UTC).timestamp())
        if (
            platform == Platform.WEB
            and self.web is not None
            and public is not None
            and auth is not None
        ):
            parsed = urlsplit(endpoint)
            payload = json.dumps(
                {"v": 1, "kind": delivery.kind.value, "tag": str(delivery.id)},
                separators=(",", ":"),
            ).encode()
            encrypted = encrypted_webpush(payload, unb64(public), unb64(auth))
            token = ec_jwt(
                self.web.private_key,
                {"alg": "ES256", "typ": "JWT"},
                {"aud": "https://" + parsed.netloc, "exp": now + 300, "sub": self.web.contact},
            )
            headers = {
                "Authorization": "vapid t=" + token + ", k=" + self.web.public_key,
                "Content-Encoding": "aes128gcm",
                "Content-Type": "application/octet-stream",
                "TTL": "0",
            }
            async with self.client.stream(
                "POST", endpoint, content=encrypted, headers=headers, follow_redirects=False
            ) as response:
                return status_outcome(response.status_code)
        if platform == Platform.IOS and self.apns is not None:
            config = self.apns
            token = ec_jwt(
                config.key,
                {"alg": "ES256", "kid": config.key_id},
                {"iss": config.team_id, "iat": now},
            )
            host = (
                "https://api.sandbox.push.apple.com"
                if config.sandbox
                else "https://api.push.apple.com"
            )
            if not endpoint.isalnum() or len(endpoint) > APNS_TOKEN_MAX:
                return Outcome.REJECTED
            async with self.client.stream(
                "POST",
                host + "/3/device/" + endpoint,
                headers={
                    "authorization": "bearer " + token,
                    "apns-topic": config.topic,
                    "apns-push-type": "alert",
                    "apns-id": str(delivery.id),
                    "apns-expiration": "0",
                },
                json={"aps": {"alert": {"title": "Peerly", "body": delivery.preview}}},
                follow_redirects=False,
            ) as response:
                return status_outcome(response.status_code)
        return Outcome.REJECTED

    async def _send_fcm(
        self, delivery: Delivery, endpoint: str, config: FcmConfiguration, access_token: str
    ) -> Outcome:
        async with self.client.stream(
            "POST",
            "https://fcm.googleapis.com/v1/projects/" + config.project + "/messages:send",
            headers={"authorization": "Bearer " + access_token},
            json={
                "message": {
                    "token": endpoint,
                    "notification": {"title": "Peerly", "body": delivery.preview},
                }
            },
            follow_redirects=False,
        ) as response:
            return status_outcome(response.status_code)


@dataclass(frozen=True, slots=True)
class ProviderSelection:
    """Explicit deployment input; none means unavailable, not a dummy success transport."""

    web: WebPushConfiguration | None = None
    apns: ApnsConfiguration | None = None
    fcm: FcmConfiguration | None = None

    def client(self) -> httpx.AsyncClient:
        # APNs requires the explicitly proposed/locked HTTP2 dependency.
        if self.apns is not None and not http2_available():
            raise ValueError("APNs requires accepted h2==4.4.1 dependency")
        return httpx.AsyncClient(
            http2=self.apns is not None,
            timeout=httpx.Timeout(2),
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=8),
            follow_redirects=False,
            trust_env=False,
        )

    def adapters(self, client: httpx.AsyncClient) -> PushProviders:
        return PushProviders(client, self.web, self.apns, self.fcm)


@dataclass(frozen=True, slots=True)
class ProviderKeyMaterial:
    web_pem: bytes | None = field(default=None, repr=False)
    contact: str | None = None
    web_hosts: tuple[str, ...] = ()
    apns_pem: bytes | None = field(default=None, repr=False)
    apns_key_id: str | None = None
    apns_team: str | None = None
    apns_topic: str | None = None
    apns_sandbox: bool = False
    fcm_pem: bytes | None = field(default=None, repr=False)
    fcm_email: str | None = field(default=None, repr=False)
    fcm_project: str | None = None


def selection_from_keys(material: ProviderKeyMaterial | None = None) -> ProviderSelection:
    """Explicit validated owner input, no discovery or secret generation."""
    material = material or ProviderKeyMaterial()
    web_pem = material.web_pem
    contact = material.contact
    web_hosts = material.web_hosts
    apns_pem = material.apns_pem
    apns_key_id = material.apns_key_id
    apns_team = material.apns_team
    apns_topic = material.apns_topic
    apns_sandbox = material.apns_sandbox
    fcm_pem = material.fcm_pem
    fcm_email = material.fcm_email
    fcm_project = material.fcm_project
    import re

    web, apns, fcm = None, None, None
    if web_pem is not None:
        key = serialization.load_pem_private_key(web_pem, password=None)
        if (
            not isinstance(key, ec.EllipticCurvePrivateKey)
            or not isinstance(key.curve, ec.SECP256R1)
            or contact is None
            or not contact.startswith(("mailto:", "https://"))
            or not web_hosts
        ):
            raise ValueError("Complete P-256 VAPID configuration required")
        if any(re.fullmatch(r"[a-z0-9.-]+", host) is None for host in web_hosts):
            raise ValueError("Exact Web Push provider hostname required")
        web = WebPushConfiguration(key, contact, web_hosts)
    elif contact is not None or web_hosts:
        raise ValueError("Partial Web Push configuration")
    if apns_pem is not None:
        key = serialization.load_pem_private_key(apns_pem, password=None)
        if (
            not isinstance(key, ec.EllipticCurvePrivateKey)
            or not isinstance(key.curve, ec.SECP256R1)
            or apns_key_id is None
            or apns_team is None
            or apns_topic is None
        ):
            raise ValueError("Complete P-256 APNs configuration required")
        if (
            re.fullmatch(r"[A-Za-z0-9]{10}", apns_key_id) is None
            or re.fullmatch(r"[A-Za-z0-9]{10}", apns_team) is None
            or re.fullmatch(r"[A-Za-z0-9.-]{1,200}", apns_topic) is None
        ):
            raise ValueError("Invalid APNs application identity")
        apns = ApnsConfiguration(key, apns_key_id, apns_team, apns_topic, apns_sandbox)
    elif any(value is not None for value in (apns_key_id, apns_team, apns_topic)):
        raise ValueError("Partial APNs configuration")
    if fcm_pem is not None:
        key = serialization.load_pem_private_key(fcm_pem, password=None)
        if (
            not isinstance(key, rsa.RSAPrivateKey)
            or fcm_email is None
            or fcm_project is None
            or re.fullmatch(r"[a-z][a-z0-9-]{4,62}", fcm_project) is None
            or not fcm_email.endswith(".iam.gserviceaccount.com")
        ):
            raise ValueError("Complete FCM service account configuration required")
        fcm = FcmConfiguration(key, fcm_project, fcm_email)
    elif fcm_email is not None or fcm_project is not None:
        raise ValueError("Partial FCM configuration")
    return ProviderSelection(web, apns, fcm)
