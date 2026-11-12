from uuid import UUID

from pydantic import AwareDatetime, Field

from studymate.application.operator.visibility_history import OperatorVisibilityHistoryPage
from studymate.domain.operator.visibility_history import (
    OPERATOR_VISIBILITY_HISTORY_PAGE_SIZE,
    OperatorVisibilityHistoryRevision,
)
from studymate.presentation.operator.models import ClosedModel


class OperatorVisibilityHistoryQuery(ClosedModel):
    cursor: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)


class OperatorVisibilityHistoryRevisionResponse(ClosedModel):
    account_id: UUID
    version: int = Field(ge=1)
    completed_at: AwareDatetime
    hidden_at: AwareDatetime | None
    changed_at: AwareDatetime


class OperatorVisibilityHistoryResponse(ClosedModel):
    account_id: UUID
    current: OperatorVisibilityHistoryRevisionResponse | None
    revisions: tuple[OperatorVisibilityHistoryRevisionResponse, ...] = Field(
        max_length=OPERATOR_VISIBILITY_HISTORY_PAGE_SIZE
    )
    next_cursor: str | None
    anchor_version: int = Field(ge=0)


def visibility_revision_response(
    value: OperatorVisibilityHistoryRevision,
) -> OperatorVisibilityHistoryRevisionResponse:
    return OperatorVisibilityHistoryRevisionResponse(
        account_id=value.account_id,
        version=value.version,
        completed_at=value.completed_at,
        hidden_at=value.hidden_at,
        changed_at=value.changed_at,
    )


def visibility_history_response(
    value: OperatorVisibilityHistoryPage,
) -> OperatorVisibilityHistoryResponse:
    return OperatorVisibilityHistoryResponse(
        account_id=value.account_id,
        current=visibility_revision_response(value.current) if value.current is not None else None,
        revisions=tuple(visibility_revision_response(row) for row in value.revisions),
        next_cursor=value.next_cursor,
        anchor_version=value.anchor_version,
    )
