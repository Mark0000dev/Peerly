"""Private closed operator DTOs. No code, placeholder or caller-selected privilege."""

from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from studymate.domain.identity import StudentEmail
from studymate.domain.operator.membership_verification import (
    ManualMembershipVerification,
    ManualVerificationBlock,
    ManualVerificationTarget,
)
from studymate.presentation.operator.models import ClosedModel


class ManualMembershipBody(ClosedModel):
    expected_google_identity_id: UUID
    expected_challenge_id: UUID
    expected_email: str = Field(min_length=1, max_length=254, repr=False)

    @model_validator(mode="after")
    def canonical_submission(self) -> Self:
        if StudentEmail(self.expected_email).value != self.expected_email:
            raise ValueError("Expected email must match the actual canonical submitted value")
        return self


class ManualMembershipResponse(ClosedModel):
    id: UUID
    account_id: UUID
    google_identity_id: UUID
    challenge_id: UUID
    operator_id: UUID
    operator_access_version: int
    actor_session_id: UUID
    event_id: UUID
    verified_at: AwareDatetime
    proof: Literal["manual_operator_attestation"] = "manual_operator_attestation"
    otp_consumed: Literal[False] = False
    activation_granted: Literal[False] = False


class SubmittedInstitutionalEmailResponse(ClosedModel):
    id: UUID
    email: str = Field(repr=False)
    created_at: AwareDatetime
    expires_at: AwareDatetime
    consumed_at: AwareDatetime | None
    superseded_at: AwareDatetime | None


class ManualMembershipContextResponse(ClosedModel):
    account_id: UUID
    google_identity_id: UUID | None
    block: ManualVerificationBlock | None
    submitted: SubmittedInstitutionalEmailResponse | None
    manual_verification: ManualMembershipResponse | None


def manual_membership_response(source: ManualMembershipVerification) -> ManualMembershipResponse:
    return ManualMembershipResponse(
        id=source.id,
        account_id=source.account_id,
        google_identity_id=source.google_identity_id,
        challenge_id=source.challenge_id,
        operator_id=source.operator.account_id,
        operator_access_version=source.operator.version,
        actor_session_id=source.actor_session_id,
        event_id=source.event_id,
        verified_at=source.verified_at,
    )


def manual_context_response(target: ManualVerificationTarget) -> ManualMembershipContextResponse:
    latest = target.latest
    return ManualMembershipContextResponse(
        account_id=target.account_id,
        google_identity_id=target.google_identity_id,
        block=target.block,
        submitted=SubmittedInstitutionalEmailResponse(
            id=latest.id,
            email=latest.email.value,
            created_at=latest.created_at,
            expires_at=latest.expires_at,
            consumed_at=latest.consumed_at,
            superseded_at=latest.superseded_at,
        )
        if latest is not None
        else None,
        manual_verification=manual_membership_response(target.manual_source)
        if target.manual_source
        else None,
    )
