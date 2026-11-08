"""Closed privileged read DTOs; no credentials, object keys or grants."""

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from studymate.application.operator.accounts import OperatorAccountPage
from studymate.application.operator.data import (
    OperatorAccountDetail,
    OperatorAccountLinkKind,
    OperatorAccountSummary,
)
from studymate.application.operator.filters import OperatorAccountFilters, OperatorAccountLifecycle
from studymate.application.operator.messages import OperatorConversationMessagesPage
from studymate.domain.identity import StudentEmail
from studymate.domain.membership import GOOGLE_ISSUER, MAX_SUBJECT_LENGTH
from studymate.domain.operator.audit import OPERATOR_ACCOUNT_PAGE_SIZE, OPERATOR_MESSAGE_PAGE_SIZE
from studymate.presentation.messaging.models import MessageResponse, message_response
from studymate.presentation.profile_models import ProfileRevisionResponse, revision_response
from studymate.presentation.registration_models import RegistrationReceiptResponse, policy_reference
from studymate.presentation.study_models import (
    GoalResponse,
    HelpResponse,
    goal_response,
    help_response,
)


class ClosedModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AccountSearchQuery(ClosedModel):
    account_id: UUID | None = None
    google_link_id: UUID | None = None
    google_issuer: str | None = Field(default=None, max_length=len(GOOGLE_ISSUER))
    google_subject: str | None = Field(
        default=None, min_length=1, max_length=MAX_SUBJECT_LENGTH, repr=False
    )
    institutional_email: str | None = Field(default=None, max_length=254, repr=False)
    name: str | None = Field(default=None, min_length=1, max_length=50, repr=False)
    lifecycle: OperatorAccountLifecycle = OperatorAccountLifecycle.ALL
    hidden: bool | None = None
    created_from: AwareDatetime | None = None
    created_before: AwareDatetime | None = None
    cursor: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)

    def filters(self) -> OperatorAccountFilters:
        return OperatorAccountFilters(
            self.account_id,
            self.google_link_id,
            self.google_issuer,
            self.google_subject,
            StudentEmail(self.institutional_email)
            if self.institutional_email is not None
            else None,
            self.name,
            self.lifecycle,
            self.hidden,
            self.created_from,
            self.created_before,
        )

    @model_validator(mode="after")
    def valid_filters(self) -> Self:
        self.filters()
        return self


class GoogleLinkResponse(ClosedModel):
    id: UUID
    issuer: str = Field(max_length=len(GOOGLE_ISSUER))
    subject: str = Field(min_length=1, max_length=MAX_SUBJECT_LENGTH, repr=False)
    created_at: datetime


class MembershipResponse(ClosedModel):
    email: str = Field(max_length=254, repr=False)
    verified_at: datetime
    revoked_at: datetime | None


class OperatorAccountResponse(ClosedModel):
    account_id: UUID
    created_at: datetime
    banned_at: datetime | None
    deleted_at: datetime | None
    google_link: GoogleLinkResponse | None = Field(repr=False)
    membership: MembershipResponse | None = Field(repr=False)
    profile_version: int | None = Field(ge=1)
    display_name: str | None = Field(max_length=50, repr=False)
    hidden_at: datetime | None


class OperatorAccountsResponse(ClosedModel):
    accounts: tuple[OperatorAccountResponse, ...] = Field(
        max_length=OPERATOR_ACCOUNT_PAGE_SIZE, repr=False
    )
    next_cursor: str | None = Field(max_length=1024, repr=False)


class PhotoReferenceResponse(ClosedModel):
    version: int = Field(ge=1)
    upload_id: UUID
    saved_at: datetime


class LifecycleResponse(ClosedModel):
    completed_at: datetime
    visibility_version: int = Field(ge=1)
    hidden_at: datetime | None
    changed_at: datetime


class ExposureResponse(ClosedModel):
    last_activity_at: datetime
    confirmed_at: datetime
    paused_at: datetime | None
    inactivity_seconds: float = Field(gt=0)


class AccountLinkResponse(ClosedModel):
    kind: OperatorAccountLinkKind
    id: UUID
    version: int | None = Field(ge=1)


class OperatorAccountDetailResponse(ClosedModel):
    account: OperatorAccountResponse = Field(repr=False)
    profile: ProfileRevisionResponse | None = Field(repr=False)
    photo: PhotoReferenceResponse | None
    goal: GoalResponse | None = Field(repr=False)
    help_subjects: HelpResponse | None = Field(repr=False)
    lifecycle: LifecycleResponse | None
    exposure: ExposureResponse | None
    registration: RegistrationReceiptResponse | None = Field(repr=False)
    links: tuple[AccountLinkResponse, ...] = Field(max_length=6)


class OperatorMessagesResponse(ClosedModel):
    conversation_id: UUID
    relationship_id: UUID
    low_id: UUID
    high_id: UUID
    request_id: UUID
    accepted_request_version: int = Field(ge=1)
    messages: tuple[MessageResponse, ...] = Field(max_length=OPERATOR_MESSAGE_PAGE_SIZE, repr=False)
    next_cursor: str | None = Field(max_length=1024, repr=False)
    anchor_sequence: int = Field(ge=0)


def account_response(value: OperatorAccountSummary) -> OperatorAccountResponse:
    google = value.google_link
    membership = value.membership.membership if value.membership is not None else None
    return OperatorAccountResponse(
        account_id=value.account_id,
        created_at=value.created_at,
        banned_at=value.banned_at,
        deleted_at=value.deleted_at,
        google_link=GoogleLinkResponse(
            id=google.id, issuer=google.issuer, subject=google.subject, created_at=google.created_at
        )
        if google is not None
        else None,
        membership=MembershipResponse(
            email=membership.email.value,
            verified_at=membership.verified_at,
            revoked_at=membership.revoked_at,
        )
        if membership is not None
        else None,
        profile_version=value.profile_version,
        display_name=value.display_name.value if value.display_name is not None else None,
        hidden_at=value.hidden_at,
    )


def accounts_response(value: OperatorAccountPage) -> OperatorAccountsResponse:
    return OperatorAccountsResponse(
        accounts=tuple(account_response(row) for row in value.accounts),
        next_cursor=value.next_cursor,
    )


def detail_response(value: OperatorAccountDetail) -> OperatorAccountDetailResponse:
    photo, lifecycle, exposure, registration = (
        value.photo,
        value.lifecycle,
        value.exposure,
        value.registration,
    )
    return OperatorAccountDetailResponse(
        account=account_response(value.account),
        profile=revision_response(value.profile) if value.profile is not None else None,
        photo=PhotoReferenceResponse(
            version=photo.version, upload_id=photo.upload_id, saved_at=photo.saved_at
        )
        if photo is not None
        else None,
        goal=goal_response(value.goal) if value.goal is not None else None,
        help_subjects=help_response(value.help_subjects)
        if value.help_subjects is not None
        else None,
        lifecycle=LifecycleResponse(
            completed_at=lifecycle.completed_at,
            visibility_version=lifecycle.visibility_version,
            hidden_at=lifecycle.hidden_at,
            changed_at=lifecycle.changed_at,
        )
        if lifecycle is not None
        else None,
        exposure=ExposureResponse(
            last_activity_at=exposure.last_activity_at,
            confirmed_at=exposure.confirmed_at,
            paused_at=exposure.paused_at,
            inactivity_seconds=exposure.inactivity.total_seconds(),
        )
        if exposure is not None
        else None,
        registration=RegistrationReceiptResponse(
            id=registration.id,
            context_id=registration.context_id,
            registered_at=registration.registered_at,
            notice_text=registration.notice_text,
            terms=policy_reference(registration.terms),
            privacy=policy_reference(registration.privacy),
            surface=registration.surface,
        )
        if registration is not None
        else None,
        links=tuple(
            AccountLinkResponse(kind=link.kind, id=link.id, version=link.version)
            for link in value.links
        ),
    )


def messages_response(value: OperatorConversationMessagesPage) -> OperatorMessagesResponse:
    conversation = value.conversation
    return OperatorMessagesResponse(
        conversation_id=conversation.id,
        relationship_id=conversation.relationship_id,
        low_id=conversation.pair.low,
        high_id=conversation.pair.high,
        request_id=conversation.request_id,
        accepted_request_version=conversation.accepted_request_version,
        messages=tuple(message_response(row) for row in value.messages),
        next_cursor=value.next_cursor,
        anchor_sequence=value.anchor_sequence,
    )
