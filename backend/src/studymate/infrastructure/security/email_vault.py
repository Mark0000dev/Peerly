import hashlib
import hmac
import secrets
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, ConfigDict, Field

from studymate.application.identity.email_delivery import DeliveryEnvelopeError, VerificationEmail
from studymate.application.identity.email_verification import VerificationCode
from studymate.domain.identity import StudentEmail
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter

KEY_BYTES = 32
NONCE_BYTES = 12


class StoredEmailBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    email: str = Field(repr=False)
    code: str = Field(repr=False)


class AeadEmailVault:
    def __init__(self, code_key: bytes, envelope_key: bytes) -> None:
        if len(code_key) != KEY_BYTES or len(envelope_key) != KEY_BYTES or code_key == envelope_key:
            raise ValueError("Email requires distinct 32-byte code and envelope keys")
        self._code_key = code_key
        self._cipher = AESGCM(envelope_key)
        self._intents = HmacIntentFingerprinter(code_key)

    async def generate_code(self) -> VerificationCode:
        return VerificationCode(f"{secrets.randbelow(1_000_000):06d}")

    async def code_digest(self, challenge_id: UUID, code: VerificationCode) -> bytes:
        return hmac.new(
            self._code_key,
            b"otp:" + challenge_id.bytes + code.value.encode("ascii"),
            hashlib.sha256,
        ).digest()

    async def fingerprint(self, parts: tuple[str, ...]) -> bytes:
        return await self._intents.fingerprint(parts)

    async def seal_delivery(
        self, challenge_id: UUID, email: StudentEmail, code: VerificationCode
    ) -> bytes:
        nonce = secrets.token_bytes(NONCE_BYTES)
        body = StoredEmailBody(email=email.value, code=code.value).model_dump_json().encode()
        return nonce + self._cipher.encrypt(nonce, body, b"email-delivery:" + challenge_id.bytes)

    async def open_delivery(self, challenge_id: UUID, payload: bytes) -> VerificationEmail:
        try:
            plaintext = self._cipher.decrypt(
                payload[:NONCE_BYTES],
                payload[NONCE_BYTES:],
                b"email-delivery:" + challenge_id.bytes,
            )
            parsed = StoredEmailBody.model_validate_json(plaintext)
            return VerificationEmail(StudentEmail(parsed.email), VerificationCode(parsed.code))
        except (InvalidTag, ValueError) as error:
            raise DeliveryEnvelopeError from error
