import hashlib

from studymate.application.identity.sessions import SessionCredential


class Sha256SessionHasher:
    """Only for server-generated 256-bit session tokens, never passwords or OTPs."""

    async def digest(self, credential: SessionCredential) -> bytes:
        return hashlib.sha256(credential.value.encode("ascii")).digest()
