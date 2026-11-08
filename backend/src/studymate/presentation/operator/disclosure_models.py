"""Closed retained technical disclosure responses, not proof that a human viewed content."""

from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from studymate.application.operator.disclosure_ports import OperatorDisclosureFilters
from studymate.application.operator.request_disclosures import OperatorRequestDisclosuresPage
from studymate.domain.operator.connection_requests import MAX_OPERATOR_REQUEST_VERSION
from studymate.domain.operator.request_disclosures import OPERATOR_DISCLOSURE_PAGE_SIZE
from studymate.presentation.operator.models import ClosedModel
from studymate.presentation.operator.request_models import (
    OperatorRequestAcknowledgementResponse,
    OperatorRequestDisclosureResponse,
    OperatorRequestRootResponse,
    acknowledgement_response,
    origin_response,
    root_response,
)


class OperatorDisclosuresQuery(ClosedModel):
    viewer_id: UUID | None = None
    stored_version: int | None = Field(default=None, ge=1, le=MAX_OPERATOR_REQUEST_VERSION)
    created_from: AwareDatetime | None = None
    created_before: AwareDatetime | None = None
    disclosure_id: UUID | None = None
    acknowledgement_id: UUID | None = None
    cursor: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)

    def filters(self) -> OperatorDisclosureFilters:
        return OperatorDisclosureFilters(
            self.viewer_id,
            self.stored_version,
            self.created_from,
            self.created_before,
            self.disclosure_id,
            self.acknowledgement_id,
        )

    @model_validator(mode="after")
    def valid_filters(self) -> Self:
        self.filters()
        return self


class OperatorRetainedDisclosureResponse(OperatorRequestDisclosureResponse):
    sender_id: UUID
    recipient_id: UUID


class OperatorDisclosuresResponse(ClosedModel):
    account_id: UUID
    request: OperatorRequestRootResponse
    disclosures: tuple[OperatorRetainedDisclosureResponse, ...] = Field(
        max_length=OPERATOR_DISCLOSURE_PAGE_SIZE
    )
    acknowledgements: tuple[OperatorRequestAcknowledgementResponse, ...] = Field(
        max_length=OPERATOR_DISCLOSURE_PAGE_SIZE
    )
    next_cursor: str | None
    anchor_created_at: AwareDatetime | None
    anchor_disclosure_id: UUID | None
    observed_at: AwareDatetime
    pagination: Literal["anchored_search_not_commit_order"] = "anchored_search_not_commit_order"
    root_observation: Literal["current_recorded_not_revision_snapshot"] = (
        "current_recorded_not_revision_snapshot"
    )
    disclosure_representation: Literal["technical_disclosure_not_ack"] = (
        "technical_disclosure_not_ack"
    )
    ack_scope: Literal["CURRENT_ACK_ROWS_FOR_PAGE_ONLY"] = "CURRENT_ACK_ROWS_FOR_PAGE_ONLY"


def disclosures_response(page: OperatorRequestDisclosuresPage) -> OperatorDisclosuresResponse:
    return OperatorDisclosuresResponse(
        account_id=page.account_id,
        request=root_response(page.request),
        disclosures=tuple(
            OperatorRetainedDisclosureResponse(
                id=row.id,
                viewer_id=row.viewer_id,
                request_id=row.request_id,
                stored_version=row.stored_version,
                sender_id=row.sender_id,
                recipient_id=row.recipient_id,
                created_at=row.created_at,
                origin=origin_response(row.origin),
            )
            for row in page.disclosures
        ),
        acknowledgements=tuple(acknowledgement_response(row) for row in page.acknowledgements),
        next_cursor=page.next_cursor,
        anchor_created_at=page.anchor_created_at,
        anchor_disclosure_id=page.anchor_disclosure_id,
        observed_at=page.observed_at,
    )
