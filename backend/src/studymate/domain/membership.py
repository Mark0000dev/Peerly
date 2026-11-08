"""Institutional verification is separate from external authentication."""

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from studymate.domain.identity import StudentEmail
from studymate.domain.time import require_aware

GOOGLE_ISSUER = "https://accounts.google.com"
MAX_CODE_ATTEMPTS = 5
MAX_SUBJECT_LENGTH = 255


@dataclass(frozen=True, slots=True)
class GoogleIdentity:
    """Only construct from a cryptographically validated provider assertion.

    This value validates shape, not signatures. Google email is intentionally
    absent: it must never identify, merge or verify a student account.
    """

    issuer: str
    subject: str

    def __post_init__(self) -> None:
        if (
            self.issuer != GOOGLE_ISSUER
            or not self.subject
            or not self.subject.isascii()
            or len(self.subject) > MAX_SUBJECT_LENGTH
        ):
            raise ValueError("Invalid Google identity")


@dataclass(frozen=True, slots=True)
class Membership:
    email: StudentEmail
    verified_at: datetime
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        require_aware(self.verified_at)
        if self.revoked_at is not None:
            require_aware(self.revoked_at)
            if self.revoked_at < self.verified_at:
                raise ValueError("Membership revocation precedes verification")

    @property
    def is_verified(self) -> bool:
        return self.revoked_at is None


class ChallengeState(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    LOCKED = "locked"
    SUPERSEDED = "superseded"
    CONSUMED = "consumed"


class AttemptOutcome(StrEnum):
    WRONG = "wrong"
    LOCKED = "locked"
    EXPIRED = "expired"
    UNAVAILABLE = "unavailable"
    VERIFIED = "verified"


@dataclass(frozen=True, slots=True)
class EmailChallenge:
    id: UUID
    account_id: UUID
    session_id: UUID
    email: StudentEmail
    created_at: datetime
    expires_at: datetime
    resend_at: datetime
    attempts: int = 0
    consumed_at: datetime | None = None
    superseded_at: datetime | None = None

    def __post_init__(self) -> None:
        for timestamp in (self.created_at, self.expires_at, self.resend_at):
            require_aware(timestamp)
        if not self.created_at < self.resend_at < self.expires_at:
            raise ValueError("Invalid challenge deadlines")
        if not 0 <= self.attempts <= MAX_CODE_ATTEMPTS:
            raise ValueError("Invalid challenge attempt count")
        for terminal_at in (self.consumed_at, self.superseded_at):
            if terminal_at is not None:
                require_aware(terminal_at)
                if terminal_at < self.created_at:
                    raise ValueError("Challenge transition precedes creation")
        if self.consumed_at is not None and self.superseded_at is not None:
            raise ValueError("Challenge cannot be consumed and superseded")

    def state(self, at: datetime) -> ChallengeState:
        require_aware(at)
        if self.consumed_at is not None:
            return ChallengeState.CONSUMED
        if self.superseded_at is not None:
            return ChallengeState.SUPERSEDED
        if self.attempts == MAX_CODE_ATTEMPTS:
            return ChallengeState.LOCKED
        if at >= self.expires_at:
            return ChallengeState.EXPIRED
        return ChallengeState.ACTIVE

    def can_resend(self, at: datetime) -> bool:
        require_aware(at)
        return self.consumed_at is None and self.superseded_at is None and at >= self.resend_at

    def supersede(self, at: datetime) -> "EmailChallenge":
        if not self.can_resend(at):
            raise ValueError("Challenge cannot be superseded yet")
        return replace(self, superseded_at=at)

    def attempt(self, *, matches: bool, at: datetime) -> tuple["EmailChallenge", AttemptOutcome]:
        current = self.state(at)
        if at < self.created_at:
            raise ValueError("Challenge attempt precedes creation")
        if current == ChallengeState.EXPIRED:
            return self, AttemptOutcome.EXPIRED
        if current == ChallengeState.LOCKED:
            return self, AttemptOutcome.LOCKED
        if current != ChallengeState.ACTIVE:
            return self, AttemptOutcome.UNAVAILABLE
        if matches:
            return replace(self, consumed_at=at), AttemptOutcome.VERIFIED
        updated = replace(self, attempts=self.attempts + 1)
        outcome = (
            AttemptOutcome.LOCKED if updated.attempts == MAX_CODE_ATTEMPTS else AttemptOutcome.WRONG
        )
        return updated, outcome


@dataclass(frozen=True, slots=True)
class IdentityCapabilities:
    can_verify_student_email: bool
    can_begin_onboarding: bool
    can_use_student_features: bool


def identity_capabilities(
    *, membership: Membership | None, banned: bool, activation_complete: bool
) -> IdentityCapabilities:
    verified = membership is not None and membership.is_verified
    return IdentityCapabilities(
        can_verify_student_email=membership is None and not banned,
        can_begin_onboarding=verified and not banned,
        can_use_student_features=verified and not banned and activation_complete,
    )
