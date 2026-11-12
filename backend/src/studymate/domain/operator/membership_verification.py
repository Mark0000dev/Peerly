"""Explicit privileged attestation of a submitted address, never OTP ownership proof."""

import base64
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from studymate.domain.identity import StudentEmail
from studymate.domain.operator.access import OperatorAccess
from studymate.domain.time import require_aware


class ManualVerificationBlock(StrEnum):
    ACCOUNT_UNAVAILABLE = "account_unavailable"
    ACCOUNT_RESTRICTED = "account_restricted"
    GOOGLE_REQUIRED = "google_identity_required"
    ALREADY_BOUND = "membership_already_bound"
    NO_SUBMISSION = "no_submitted_email"
    NOT_PENDING = "challenge_not_pending"
    STAGING_PLACEHOLDER = "staging_placeholder_not_allowed"


@dataclass(frozen=True, slots=True)
class SubmittedInstitutionalEmail:
    id: UUID
    account_id: UUID
    email: StudentEmail = field(repr=False)
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None
    superseded_at: datetime | None = None

    def __post_init__(self) -> None:
        for at in (self.created_at, self.expires_at, self.consumed_at, self.superseded_at):
            if at is not None:
                require_aware(at)
        if self.expires_at <= self.created_at:
            raise ValueError("Submitted email needs its actual ordered challenge timestamps")

    @property
    def is_staging_placeholder(self) -> bool:
        return (
            re.fullmatch(r"peerly-stage-[0-9a-f]{32}@mail\.apu\.edu\.my", self.email.value)
            is not None
        )


@dataclass(frozen=True, slots=True)
class ManualVerificationTarget:
    account_id: UUID
    google_identity_id: UUID | None
    deleted: bool
    banned: bool
    lineage_banned: bool
    has_binding: bool
    latest: SubmittedInstitutionalEmail | None
    manual_source: "ManualMembershipVerification | None" = None

    def __post_init__(self) -> None:
        if self.manual_source is not None and self.manual_source.account_id != self.account_id:
            raise ValueError("Manual context cannot borrow another account's attestation")
        if self.latest is not None and self.latest.account_id != self.account_id:
            raise ValueError("Manual verification cannot borrow another account's submission")

    @property
    def block(self) -> ManualVerificationBlock | None:
        latest = self.latest
        rules = (
            (self.deleted, ManualVerificationBlock.ACCOUNT_UNAVAILABLE),
            (self.banned or self.lineage_banned, ManualVerificationBlock.ACCOUNT_RESTRICTED),
            (self.google_identity_id is None, ManualVerificationBlock.GOOGLE_REQUIRED),
            (self.has_binding, ManualVerificationBlock.ALREADY_BOUND),
            (latest is None, ManualVerificationBlock.NO_SUBMISSION),
            (
                latest is not None and latest.is_staging_placeholder,
                ManualVerificationBlock.STAGING_PLACEHOLDER,
            ),
            (
                latest is not None
                and (latest.consumed_at is not None or latest.superseded_at is not None),
                ManualVerificationBlock.NOT_PENDING,
            ),
        )
        # Expiry/failed delivery are not an OTP. Explicit manual attestation may still apply.
        return next((reason for blocked, reason in rules if blocked), None)


@dataclass(frozen=True, slots=True)
class ManualMembershipVerification:
    id: UUID
    account_id: UUID
    google_identity_id: UUID
    challenge_id: UUID
    operator: OperatorAccess
    actor_session_id: UUID
    event_id: UUID
    email: StudentEmail = field(repr=False)
    verified_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.verified_at)
        if not self.operator.is_active(self.verified_at):
            raise ValueError("Manual attestation needs its actual active operator grant revision")

    @property
    def occurrence_key(self) -> str:
        encoded = base64.urlsafe_b64encode(self.challenge_id.bytes).decode("ascii").rstrip("=")
        return f"smv1:{self.id.hex}:c{encoded}:{self.operator.account_id.hex}"
