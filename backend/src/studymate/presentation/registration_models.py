from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from studymate.domain.registration import (
    PolicyKind,
    PolicyReference,
    RegistrationContext,
    RegistrationReceipt,
    RegistrationSurface,
)


class PolicyReferenceResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID
    kind: PolicyKind
    version: str
    published_at: datetime


class RegistrationContextResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID
    expires_at: datetime
    notice_text: str
    terms: PolicyReferenceResponse
    privacy: PolicyReferenceResponse
    surface: RegistrationSurface


class RegistrationReceiptResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID
    context_id: UUID
    registered_at: datetime
    notice_text: str
    terms: PolicyReferenceResponse
    privacy: PolicyReferenceResponse
    surface: RegistrationSurface


class PolicyStatusResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    receipt: RegistrationReceiptResponse | None
    current_terms: PolicyReferenceResponse | None
    current_privacy: PolicyReferenceResponse | None


class PublishedPolicyResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    reference: PolicyReferenceResponse
    title: str
    content: str


class CompleteRegistrationRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    context_id: UUID


def policy_reference(value: PolicyReference) -> PolicyReferenceResponse:
    return PolicyReferenceResponse(
        id=value.id, kind=value.kind, version=value.version.value, published_at=value.published_at
    )


def context_response(value: RegistrationContext) -> RegistrationContextResponse:
    return RegistrationContextResponse(
        id=value.id,
        expires_at=value.expires_at,
        notice_text=value.notice_text,
        terms=policy_reference(value.terms),
        privacy=policy_reference(value.privacy),
        surface=value.surface,
    )


def receipt_response(value: RegistrationReceipt) -> RegistrationReceiptResponse:
    return RegistrationReceiptResponse(
        id=value.id,
        context_id=value.context.id,
        registered_at=value.registered_at,
        notice_text=value.context.notice_text,
        terms=policy_reference(value.context.terms),
        privacy=policy_reference(value.context.privacy),
        surface=value.context.surface,
    )
