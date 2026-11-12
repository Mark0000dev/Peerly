"""Privileged retained lifecycle provenance; private reason stays out of repr."""

from uuid import UUID

from pydantic import AwareDatetime, Field

from studymate.application.operator.lifecycle_history import OperatorLifecycleHistoryPage
from studymate.domain.lifecycle.states import LifecycleOperation
from studymate.domain.operator.lifecycle_history import OPERATOR_LIFECYCLE_HISTORY_PAGE_SIZE
from studymate.presentation.operator.models import ClosedModel


class OperatorLifecycleHistoryQuery(ClosedModel):
    cursor: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)


class OperatorLifecycleHistoryRevisionResponse(ClosedModel):
    id: UUID
    account_id: UUID
    version: int = Field(ge=1)
    previous_version: int | None
    operation: LifecycleOperation
    before_banned_at: AwareDatetime | None
    before_deleted_at: AwareDatetime | None
    after_banned_at: AwareDatetime | None
    after_deleted_at: AwareDatetime | None
    changed_at: AwareDatetime
    actor_id: UUID
    actor_session_id: UUID
    operator_access_version: int | None
    operator_access_active: bool | None
    reason: str | None = Field(repr=False)
    workflow_id: UUID | None
    http_request_id: UUID | None
    action_id: UUID | None
    trace_id: str | None
    span_id: str | None


class OperatorLifecycleHistoryResponse(ClosedModel):
    account_id: UUID
    revisions: tuple[OperatorLifecycleHistoryRevisionResponse, ...] = Field(
        max_length=OPERATOR_LIFECYCLE_HISTORY_PAGE_SIZE, repr=False
    )
    next_cursor: str | None
    anchor_version: int = Field(ge=0)


def lifecycle_history_response(
    value: OperatorLifecycleHistoryPage,
) -> OperatorLifecycleHistoryResponse:
    return OperatorLifecycleHistoryResponse(
        account_id=value.account_id,
        revisions=tuple(
            OperatorLifecycleHistoryRevisionResponse(
                id=row.id,
                account_id=row.account_id,
                version=row.version,
                previous_version=row.previous_version,
                operation=row.operation,
                before_banned_at=row.before_banned_at,
                before_deleted_at=row.before_deleted_at,
                after_banned_at=row.after_banned_at,
                after_deleted_at=row.after_deleted_at,
                changed_at=row.changed_at,
                actor_id=row.actor_id,
                actor_session_id=row.actor_session_id,
                operator_access_version=row.operator_access_version,
                operator_access_active=row.operator_access_active,
                reason=row.reason,
                workflow_id=row.workflow_id,
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
