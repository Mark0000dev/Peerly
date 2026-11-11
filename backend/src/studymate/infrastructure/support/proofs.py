import hashlib
import secrets
from dataclasses import dataclass

from studymate.application.support.cases import SupportCredential


@dataclass(frozen=True, slots=True)
class OpaqueSupportProofs:
    def issue(self) -> SupportCredential:
        return SupportCredential(secrets.token_urlsafe(32))

    def digest(self, credential: SupportCredential) -> bytes:
        return hashlib.sha256(
            b"peerly.support.proof.v1:" + credential.value.encode("ascii")
        ).digest()
