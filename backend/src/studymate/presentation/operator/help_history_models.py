"""Exact historical help declarations, not a current subject picker or inferred proficiency."""

from uuid import UUID

from pydantic import AwareDatetime, Field

from studymate.application.operator.help_history import OperatorHelpHistoryPage
from studymate.domain.operator.help_history import (
    OPERATOR_HELP_HISTORY_PAGE_SIZE,
    OperatorHelpHistoryRevision,
    OperatorHelpHistorySelection,
)
from studymate.presentation.operator.models import ClosedModel


class OperatorHelpHistoryQuery(ClosedModel):
    cursor: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)


class OperatorHelpHistorySelectionResponse(ClosedModel):
    slot: int = Field(ge=0)
    subject_id: UUID
    subject_label: str = Field(repr=False)
    topic_note: str | None = Field(repr=False)
    topic_match_key: str | None = Field(repr=False)


class OperatorHelpHistoryRevisionResponse(ClosedModel):
    account_id: UUID
    version: int = Field(ge=1)
    selections: tuple[OperatorHelpHistorySelectionResponse, ...] = Field(repr=False)
    saved_at: AwareDatetime


class OperatorHelpHistoryResponse(ClosedModel):
    account_id: UUID
    revisions: tuple[OperatorHelpHistoryRevisionResponse, ...] = Field(
        max_length=OPERATOR_HELP_HISTORY_PAGE_SIZE, repr=False
    )
    next_cursor: str | None
    anchor_version: int = Field(ge=0)


def help_selection_response(
    value: OperatorHelpHistorySelection,
) -> OperatorHelpHistorySelectionResponse:
    return OperatorHelpHistorySelectionResponse(
        slot=value.slot,
        subject_id=value.subject_id,
        subject_label=value.subject_label,
        topic_note=value.topic_note,
        topic_match_key=value.topic_match_key,
    )


def help_history_revision_response(
    value: OperatorHelpHistoryRevision,
) -> OperatorHelpHistoryRevisionResponse:
    return OperatorHelpHistoryRevisionResponse(
        account_id=value.account_id,
        version=value.version,
        selections=tuple(help_selection_response(selection) for selection in value.selections),
        saved_at=value.saved_at,
    )


def help_history_response(value: OperatorHelpHistoryPage) -> OperatorHelpHistoryResponse:
    return OperatorHelpHistoryResponse(
        account_id=value.account_id,
        revisions=tuple(help_history_revision_response(row) for row in value.revisions),
        next_cursor=value.next_cursor,
        anchor_version=value.anchor_version,
    )
