import re
from dataclasses import dataclass, field
from typing import Protocol


class IdempotencyConflictError(Exception):
    pass


class IntentFingerprinter(Protocol):
    async def fingerprint(self, parts: tuple[str, ...]) -> bytes: ...


@dataclass(frozen=True, slots=True)
class IntentKey:
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", self.value):
            raise ValueError("Invalid idempotency key")
