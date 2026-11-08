"""Exact retained profile history, not a student form/current-photo disclosure."""

from uuid import UUID

from pydantic import AwareDatetime, Field

from studymate.application.operator.profile_history import OperatorProfileHistoryPage
from studymate.domain.operator.profile_history import (
    OPERATOR_PROFILE_HISTORY_PAGE_SIZE,
    OperatorProfileHistoryRevision,
)
from studymate.domain.profiles import OnboardingTask
from studymate.presentation.operator.models import ClosedModel


class OperatorProfileHistoryQuery(ClosedModel):
    cursor: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)


class OperatorProfileHistoryRevisionResponse(ClosedModel):
    account_id: UUID
    version: int = Field(ge=1)
    display_name: str | None = Field(repr=False)
    about: str | None = Field(repr=False)
    programme: str | None = Field(repr=False)
    year_label: str | None = Field(repr=False)
    languages: tuple[str, ...] = Field(repr=False)
    task: OnboardingTask
    saved_at: AwareDatetime


class OperatorProfileHistoryResponse(ClosedModel):
    account_id: UUID
    revisions: tuple[OperatorProfileHistoryRevisionResponse, ...] = Field(
        max_length=OPERATOR_PROFILE_HISTORY_PAGE_SIZE, repr=False
    )
    next_cursor: str | None
    anchor_version: int = Field(ge=0)


def history_revision_response(
    value: OperatorProfileHistoryRevision,
) -> OperatorProfileHistoryRevisionResponse:
    return OperatorProfileHistoryRevisionResponse(
        account_id=value.account_id,
        version=value.version,
        display_name=value.display_name,
        about=value.about,
        programme=value.programme,
        year_label=value.year_label,
        languages=value.languages,
        task=value.task,
        saved_at=value.saved_at,
    )


def profile_history_response(value: OperatorProfileHistoryPage) -> OperatorProfileHistoryResponse:
    return OperatorProfileHistoryResponse(
        account_id=value.account_id,
        revisions=tuple(history_revision_response(row) for row in value.revisions),
        next_cursor=value.next_cursor,
        anchor_version=value.anchor_version,
    )
