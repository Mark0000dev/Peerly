from uuid import UUID

from pydantic import AwareDatetime, Field

from studymate.application.operator.preference_history import OperatorPreferenceHistoryPage
from studymate.domain.notification_preferences.state import NotificationMode
from studymate.domain.operator.preference_history import (
    OPERATOR_PREFERENCE_HISTORY_PAGE_SIZE,
    OperatorPreferenceHistoryRevision,
)
from studymate.presentation.operator.models import ClosedModel


class OperatorPreferenceHistoryQuery(ClosedModel):
    cursor: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)


class OperatorPreferenceHistoryRevisionResponse(ClosedModel):
    account_id: UUID
    version: int = Field(ge=1)
    mode: NotificationMode
    changed_at: AwareDatetime


class OperatorPreferenceHistoryResponse(ClosedModel):
    account_id: UUID
    current: OperatorPreferenceHistoryRevisionResponse | None
    revisions: tuple[OperatorPreferenceHistoryRevisionResponse, ...] = Field(
        max_length=OPERATOR_PREFERENCE_HISTORY_PAGE_SIZE
    )
    next_cursor: str | None
    anchor_version: int = Field(ge=0)


def preference_revision_response(
    value: OperatorPreferenceHistoryRevision,
) -> OperatorPreferenceHistoryRevisionResponse:
    return OperatorPreferenceHistoryRevisionResponse(
        account_id=value.account_id,
        version=value.version,
        mode=value.mode,
        changed_at=value.changed_at,
    )


def preference_history_response(
    value: OperatorPreferenceHistoryPage,
) -> OperatorPreferenceHistoryResponse:
    return OperatorPreferenceHistoryResponse(
        account_id=value.account_id,
        current=preference_revision_response(value.current) if value.current is not None else None,
        revisions=tuple(preference_revision_response(row) for row in value.revisions),
        next_cursor=value.next_cursor,
        anchor_version=value.anchor_version,
    )
