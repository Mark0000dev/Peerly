"""Private stored-claim facts; no login tokens, challenges or asserted person identity."""

from uuid import UUID

from pydantic import AwareDatetime, Field

from studymate.application.operator.identity_links import OperatorIdentityLinksPage
from studymate.application.operator.identity_links_data import (
    IDENTITY_LINKS_PAGE_SIZE,
    OperatorIdentityAccount,
)
from studymate.presentation.operator.models import ClosedModel


class OperatorIdentityLinksQuery(ClosedModel):
    cursor: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)


class OperatorGoogleClaimResponse(ClosedModel):
    id: UUID
    issuer: str
    subject: str = Field(repr=False)
    created_at: AwareDatetime
    retired_at: AwareDatetime | None


class OperatorInstitutionalClaimResponse(ClosedModel):
    email: str = Field(repr=False)
    verified_at: AwareDatetime
    revoked_at: AwareDatetime | None
    retired_at: AwareDatetime | None


class OperatorIdentityAccountResponse(ClosedModel):
    account_id: UUID
    created_at: AwareDatetime
    banned_at: AwareDatetime | None
    deleted_at: AwareDatetime | None
    google: OperatorGoogleClaimResponse | None = Field(repr=False)
    institutional: OperatorInstitutionalClaimResponse | None = Field(repr=False)


class OperatorIdentityLinkResponse(ClosedModel):
    account: OperatorIdentityAccountResponse = Field(repr=False)
    shared_google_claim: bool
    shared_institutional_email: bool


class OperatorIdentityLinksResponse(ClosedModel):
    target: OperatorIdentityAccountResponse = Field(repr=False)
    links: tuple[OperatorIdentityLinkResponse, ...] = Field(
        max_length=IDENTITY_LINKS_PAGE_SIZE, repr=False
    )
    next_cursor: str | None
    as_of: AwareDatetime


def identity_account_response(value: OperatorIdentityAccount) -> OperatorIdentityAccountResponse:
    google = value.google
    institutional = value.institutional
    return OperatorIdentityAccountResponse(
        account_id=value.account_id,
        created_at=value.created_at,
        banned_at=value.banned_at,
        deleted_at=value.deleted_at,
        google=OperatorGoogleClaimResponse(
            id=google.id,
            issuer=google.issuer,
            subject=google.subject,
            created_at=google.created_at,
            retired_at=google.retired_at,
        )
        if google is not None
        else None,
        institutional=OperatorInstitutionalClaimResponse(
            email=institutional.email.value,
            verified_at=institutional.verified_at,
            revoked_at=institutional.revoked_at,
            retired_at=institutional.retired_at,
        )
        if institutional is not None
        else None,
    )


def identity_links_response(value: OperatorIdentityLinksPage) -> OperatorIdentityLinksResponse:
    return OperatorIdentityLinksResponse(
        target=identity_account_response(value.target),
        links=tuple(
            OperatorIdentityLinkResponse(
                account=identity_account_response(row.account),
                shared_google_claim=row.shared_google_claim,
                shared_institutional_email=row.shared_institutional_email,
            )
            for row in value.links
        ),
        next_cursor=value.next_cursor,
        as_of=value.as_of,
    )
