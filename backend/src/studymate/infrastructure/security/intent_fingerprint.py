import hashlib
import hmac
import json
from dataclasses import dataclass, field

KEY_BYTES = 32


@dataclass(frozen=True, slots=True)
class HmacIntentFingerprinter:
    key: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if len(self.key) != KEY_BYTES:
            raise ValueError("Intent fingerprint key must have 32 bytes")

    async def fingerprint(self, parts: tuple[str, ...]) -> bytes:
        return hmac.new(
            self.key,
            b"intent:" + json.dumps(parts, ensure_ascii=True).encode("ascii"),
            hashlib.sha256,
        ).digest()
