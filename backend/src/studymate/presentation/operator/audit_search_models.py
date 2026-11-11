"""Closed audit metadata search; existing detail DTO preserves typed actual sources."""

from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from studymate.application.operator.audit_search import OperatorAuditsPage
from studymate.application.operator.audit_search_ports import OperatorAuditFilters
from studymate.domain.operator.audit import (
    OPERATOR_EVENT_PAGE_SIZE,
    OperatorAction,
    OperatorResourceKind,
)
from studymate.presentation.operator.models import ClosedModel
from studymate.presentation.operator.timeline_models import (
    OperatorAuditDetailResponse,
    audit_response,
)


class OperatorAuditQuery(ClosedModel):
    operator_id: UUID | None = None
    action: OperatorAction | None = None
    requested_kind: OperatorResourceKind | None = None
    requested_id: UUID | None = None
    http_request_id: UUID | None = None
    action_id: UUID | None = None
    trace_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$", repr=False)
    occurred_from: AwareDatetime | None = None
    occurred_before: AwareDatetime | None = None
    cursor: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)

    def filters(self) -> OperatorAuditFilters:
        return OperatorAuditFilters(
            self.operator_id,
            self.action,
            self.requested_kind,
            self.requested_id,
            self.http_request_id,
            self.action_id,
            self.trace_id,
            self.occurred_from,
            self.occurred_before,
        )

    @model_validator(mode="after")
    def valid_filters(self) -> Self:
        self.filters()
        return self


class OperatorAuditsResponse(ClosedModel):
    audits: tuple[OperatorAuditDetailResponse, ...] = Field(max_length=OPERATOR_EVENT_PAGE_SIZE)
    next_cursor: str | None
    search_anchor_at: AwareDatetime


def audits_response(page: OperatorAuditsPage) -> OperatorAuditsResponse:
    return OperatorAuditsResponse(
        audits=tuple(audit_response(row) for row in page.audits),
        next_cursor=page.next_cursor,
        search_anchor_at=page.search_anchor_at,
    )
