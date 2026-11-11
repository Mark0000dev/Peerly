import hashlib
import hmac

from studymate.application.identity.sessions import SessionCredential

SIGNING_KEY_BYTES = 32


class HmacBrowserTokenSigner:
    def __init__(self, key: bytes) -> None:
        if len(key) != SIGNING_KEY_BYTES:
            raise ValueError("Browser signing key must have 32 bytes")
        self._key = key

    async def csrf_token(self, credential: SessionCredential) -> str:
        return hmac.new(
            self._key, b"csrf:" + credential.value.encode("ascii"), hashlib.sha256
        ).hexdigest()

    async def valid_csrf(self, credential: SessionCredential, token: str) -> bool:
        if not token.isascii():
            return False
        return hmac.compare_digest(await self.csrf_token(credential), token)

    async def source_digest(self, address: str) -> bytes:
        return hmac.new(self._key, b"source:" + address.encode("utf-8"), hashlib.sha256).digest()
