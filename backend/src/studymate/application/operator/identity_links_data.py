"""Retained stored-claim associations, never proof that two accounts are one person."""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from studymate.domain.identity import StudentEmail
from studymate.domain.membership import GOOGLE_ISSUER, MAX_SUBJECT_LENGTH
from studymate.domain.time import require_aware

IDENTITY_LINKS_PAGE_SIZE = 50


@dataclass(frozen=True, slots=True)
class OperatorGoogleClaim:
    id: UUID
    issuer: str
    subject: str = field(repr=False)
    created_at: datetime
    retired_at: datetime | None

    def __post_init__(self) -> None:
        require_aware(self.created_at)
        if self.retired_at is not None:
            require_aware(self.retired_at)
        if (
            self.issuer != GOOGLE_ISSUER
            or not self.subject
            or len(self.subject) > MAX_SUBJECT_LENGTH
            or not self.subject.isascii()
        ):
            raise ValueError("Invalid retained Google claim")


@dataclass(frozen=True, slots=True)
class OperatorInstitutionalClaim:
    email: StudentEmail = field(repr=False)
    verified_at: datetime
    revoked_at: datetime | None
    retired_at: datetime | None

    def __post_init__(self) -> None:
        require_aware(self.verified_at)
        for value in (self.revoked_at, self.retired_at):
            if value is not None:
                require_aware(value)


@dataclass(frozen=True, slots=True)
class OperatorIdentityAccount:
    account_id: UUID
    created_at: datetime
    banned_at: datetime | None
    deleted_at: datetime | None
    google: OperatorGoogleClaim | None = field(repr=False)
    institutional: OperatorInstitutionalClaim | None = field(repr=False)

    def __post_init__(self) -> None:
        require_aware(self.created_at)
        for value in (self.banned_at, self.deleted_at):
            if value is not None:
                require_aware(value)

    def claim_fingerprint(self) -> bytes:
        # Only immutable source keys bind pagination; live retirement is a current fact.
        values = (
            (str(self.google.id), self.google.issuer, self.google.subject)
            if self.google is not None
            else None,
            (
                self.institutional.email.value,
                self.institutional.verified_at.astimezone(UTC).isoformat(),
            )
            if self.institutional is not None
            else None,
        )
        return hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).digest()


@dataclass(frozen=True, slots=True)
class OperatorIdentityLink:
    account: OperatorIdentityAccount = field(repr=False)
    shared_google_claim: bool
    shared_institutional_email: bool

    def __post_init__(self) -> None:
        if not self.shared_google_claim and not self.shared_institutional_email:
            raise ValueError("A retained association requires an actual direct shared claim")
