"""Provider-independent identity values; these do not establish authentication."""

import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from uuid import UUID

from studymate.domain.time import require_aware

_STUDENT_ADDRESS = re.compile(r"[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*")
_STUDENT_DOMAIN = "mail.apu.edu.my"
_MAX_LOCAL_LENGTH = 64


@dataclass(frozen=True, slots=True)
class StudentEmail:
    """Canonical institutional address, not evidence of mailbox ownership.

    Accept ASCII dot-atom addresses only. Preserve dots and plus tags: neither
    implies an alias policy at the university. Repr excludes the private address.
    """

    value: str = field(repr=False)

    def __post_init__(self) -> None:
        canonical = self.value.strip().lower()
        local, separator, domain = canonical.partition("@")
        if (
            not self.value.isascii()
            or separator != "@"
            or domain != _STUDENT_DOMAIN
            or len(local) > _MAX_LOCAL_LENGTH
            or not _STUDENT_ADDRESS.fullmatch(local)
        ):
            raise ValueError("A valid institutional student email is required")
        object.__setattr__(self, "value", canonical)


@dataclass(frozen=True, slots=True)
class Session:
    """Stored session lifecycle, with no bearer secret or provider-specific data."""

    id: UUID
    account_id: UUID
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        require_aware(self.issued_at)
        require_aware(self.expires_at)
        if self.expires_at <= self.issued_at:
            raise ValueError("Session expiry must follow issuance")
        if self.revoked_at is not None:
            require_aware(self.revoked_at)
            if self.revoked_at < self.issued_at:
                raise ValueError("Session revocation cannot precede issuance")

    def is_active(self, at: datetime) -> bool:
        require_aware(at)
        return self.revoked_at is None and self.issued_at <= at < self.expires_at

    def revoke(self, at: datetime) -> "Session":
        require_aware(at)
        if at < self.issued_at:
            raise ValueError("Session revocation cannot precede issuance")
        if self.revoked_at is not None:
            return self
        return replace(self, revoked_at=at)
