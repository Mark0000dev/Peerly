from typing import Protocol

from studymate.application.identity.sessions import SessionCredential


class BrowserTokenSigner(Protocol):
    async def csrf_token(self, credential: SessionCredential) -> str: ...

    async def valid_csrf(self, credential: SessionCredential, token: str) -> bool: ...

    async def source_digest(self, address: str) -> bytes: ...
