"""Stored permission history with truthful nullable legacy attribution."""

from uuid import UUID

from pydantic import AwareDatetime, Field

from studymate.application.operator.access_history import OperatorAccessHistoryPage
from studymate.domain.operator.access_history import OPERATOR_ACCESS_HISTORY_PAGE_SIZE
from studymate.presentation.operator.models import ClosedModel


class OperatorAccessHistoryQuery(ClosedModel):
    cursor: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)


class OperatorAccessHistoryRevisionResponse(ClosedModel):
    account_id: UUID
    version: int = Field(ge=1)
    active: bool
    changed_at: AwareDatetime
    changed_by_id: UUID | None
    http_request_id: UUID | None
    action_id: UUID | None
    trace_id: str | None
    span_id: str | None


class OperatorAccessHistoryResponse(ClosedModel):
    account_id: UUID
    revisions: tuple[OperatorAccessHistoryRevisionResponse, ...] = Field(
        max_length=OPERATOR_ACCESS_HISTORY_PAGE_SIZE
    )
    next_cursor: str | None
    anchor_version: int = Field(ge=0)


def access_history_response(value: OperatorAccessHistoryPage) -> OperatorAccessHistoryResponse:
    return OperatorAccessHistoryResponse(
        account_id=value.account_id,
        revisions=tuple(
            OperatorAccessHistoryRevisionResponse(
                account_id=row.account_id,
                version=row.version,
                active=row.active,
                changed_at=row.changed_at,
                changed_by_id=row.changed_by_id,
                http_request_id=row.http_request_id,
                action_id=row.action_id,
                trace_id=row.trace_id,
                span_id=row.span_id,
            )
            for row in value.revisions
        ),
        next_cursor=value.next_cursor,
        anchor_version=value.anchor_version,
    )
