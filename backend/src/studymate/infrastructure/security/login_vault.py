import hashlib
import json
import secrets
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, ConfigDict, ValidationError

from studymate.application.identity.google import GoogleAuthorization, GoogleRejectedError
from studymate.application.identity.login import LoginMaterial
from studymate.application.identity.sessions import SessionCredential

NONCE_BYTES = 12
KEY_BYTES = 32


class StoredAuthorization(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    state: str
    nonce: str
    verifier: str


class AeadLoginVault:
    def __init__(self, key: bytes) -> None:
        if len(key) != KEY_BYTES:
            raise ValueError("Login encryption key must have 32 bytes")
        self._cipher = AESGCM(key)

    async def generate(self) -> LoginMaterial:
        return LoginMaterial(
            GoogleAuthorization(
                secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            ),
            SessionCredential(secrets.token_urlsafe(32)),
        )

    async def session_credential(self) -> SessionCredential:
        return SessionCredential(secrets.token_urlsafe(32))

    async def digest(self, value: str) -> bytes:
        return hashlib.sha256(value.encode("utf-8")).digest()

    async def seal(self, material: GoogleAuthorization, flow_id: UUID) -> bytes:
        nonce = secrets.token_bytes(NONCE_BYTES)
        payload = json.dumps(
            {"state": material.state, "nonce": material.nonce, "verifier": material.verifier}
        ).encode()
        return nonce + self._cipher.encrypt(nonce, payload, b"oidc-login:" + flow_id.bytes)

    async def open(self, payload: bytes, flow_id: UUID) -> GoogleAuthorization:
        try:
            plaintext = self._cipher.decrypt(
                payload[:NONCE_BYTES], payload[NONCE_BYTES:], b"oidc-login:" + flow_id.bytes
            )
            parsed = StoredAuthorization.model_validate_json(plaintext)
        except (InvalidTag, ValueError, ValidationError) as error:
            raise GoogleRejectedError from error
        return GoogleAuthorization(parsed.state, parsed.nonce, parsed.verifier)
