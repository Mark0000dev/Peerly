from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from studymate.application.support.operator_inbox import (
    OperatorSupportHistoryPage,
    OperatorSupportInboxPage,
)
from studymate.application.support.operator_inbox_ports import OperatorSupportFilters
from studymate.domain.support.cases import SupportStatus, SupportTopic
from studymate.domain.support.operator_inbox import OPERATOR_SUPPORT_PAGE_SIZE


class OperatorSupportInboxQuery(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    case_id: UUID | None = None
    actor_id: UUID | None = None
    topic: SupportTopic | None = None
    status: SupportStatus | None = None
    anonymous: bool | None = None
    received_from: AwareDatetime | None = None
    received_before: AwareDatetime | None = None
    cursor: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)

    @model_validator(mode="after")
    def valid_filters(self) -> "OperatorSupportInboxQuery":
        self.filters()
        return self

    def filters(self) -> OperatorSupportFilters:
        return OperatorSupportFilters(
            case_id=self.case_id,
            actor_id=self.actor_id,
            topic=self.topic,
            status=self.status,
            anonymous=self.anonymous,
            received_from=self.received_from,
            received_before=self.received_before,
        )


class OperatorSupportHistoryQuery(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    cursor: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)


class OperatorSupportSummaryResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    case_id: UUID
    actor_id: UUID | None
    topic: SupportTopic
    received_at: AwareDatetime
    status: SupportStatus
    version: int = Field(ge=1)
    changed_at: AwareDatetime


class OperatorSupportInboxResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    cases: tuple[OperatorSupportSummaryResponse, ...] = Field(max_length=OPERATOR_SUPPORT_PAGE_SIZE)
    next_cursor: str | None
    metadata_anchor: AwareDatetime
    status_semantics: Literal["current_at_each_request"] = "current_at_each_request"


class OperatorSupportHistoryRevisionResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    version: int = Field(ge=1)
    status: SupportStatus
    changed_at: AwareDatetime
    changed_by_id: UUID | None
    operator_access_version: int | None = Field(ge=1)


class OperatorSupportHistoryResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    case_id: UUID
    anchor_version: int = Field(ge=1)
    revisions: tuple[OperatorSupportHistoryRevisionResponse, ...] = Field(
        max_length=OPERATOR_SUPPORT_PAGE_SIZE
    )
    next_cursor: str | None


def inbox_response(page: OperatorSupportInboxPage) -> OperatorSupportInboxResponse:
    return OperatorSupportInboxResponse(
        cases=tuple(
            OperatorSupportSummaryResponse(
                case_id=row.receipt.case_id,
                actor_id=row.actor_id,
                topic=row.topic,
                received_at=row.receipt.received_at,
                status=row.receipt.status,
                version=row.receipt.version,
                changed_at=row.receipt.changed_at,
            )
            for row in page.cases
        ),
        next_cursor=page.next_cursor,
        metadata_anchor=page.metadata_anchor,
    )


def history_response(page: OperatorSupportHistoryPage) -> OperatorSupportHistoryResponse:
    return OperatorSupportHistoryResponse(
        case_id=page.case_id,
        anchor_version=page.anchor_version,
        revisions=tuple(
            OperatorSupportHistoryRevisionResponse(
                version=row.receipt.version,
                status=row.receipt.status,
                changed_at=row.receipt.changed_at,
                changed_by_id=row.changed_by_id,
                operator_access_version=row.operator_access_version,
            )
            for row in page.revisions
        ),
        next_cursor=page.next_cursor,
    )
