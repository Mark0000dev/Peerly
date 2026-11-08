"""Domain-separated, reproducible proof for an unresolved deletion workflow only."""

import base64
import hashlib
import hmac
from dataclasses import dataclass, field

from studymate.application.lifecycle.deletion_ports import DeletionWorkflowAuthorization
from studymate.application.lifecycle.recovery import DeletionStatusCredential

PROOF_KEY_BYTES = 32
SESSION_DIGEST_BYTES = 32


@dataclass(frozen=True, slots=True)
class HmacDeletionStatusProofs:
    key: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if len(self.key) != PROOF_KEY_BYTES:
            raise ValueError("Deletion status derivation requires its server key")

    def issue(
        self, authorization: DeletionWorkflowAuthorization, session_digest: bytes
    ) -> DeletionStatusCredential:
        if len(session_digest) != SESSION_DIGEST_BYTES:
            raise ValueError("Deletion status derivation requires the original session digest")
        message = (
            b"peerly.deletion.outcome.v1\x00"
            + authorization.id.bytes
            + authorization.account_id.bytes
            + authorization.session_id.bytes
            + session_digest
        )
        value = hmac.digest(self.key, message, "sha256")
        return DeletionStatusCredential(
            base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")
        )

    def digest(self, credential: DeletionStatusCredential) -> bytes:
        return hashlib.sha256(
            b"peerly.deletion.outcome.lookup.v1\x00" + credential.value.encode("ascii")
        ).digest()
