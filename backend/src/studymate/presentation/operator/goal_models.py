"""Closed raw goal roots/history; metadata anchors are not commit-order or student authority."""

from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from studymate.application.operator.goal_ports import OperatorGoalFilters, OperatorGoalState
from studymate.application.operator.goals import OperatorGoalHistoryPage, OperatorGoalsPage
from studymate.domain.operator.goals import (
    OPERATOR_GOAL_PAGE_SIZE,
    OperatorGoalRevision,
    OperatorGoalRoot,
)
from studymate.presentation.operator.models import ClosedModel


class OperatorGoalsQuery(ClosedModel):
    state: OperatorGoalState | None = None
    created_from: AwareDatetime | None = None
    created_before: AwareDatetime | None = None
    cursor: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)

    def filters(self) -> OperatorGoalFilters:
        return OperatorGoalFilters(self.state, self.created_from, self.created_before)

    @model_validator(mode="after")
    def valid_filters(self) -> Self:
        self.filters()
        return self


class OperatorGoalHistoryQuery(ClosedModel):
    cursor: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)


class OperatorGoalRootResponse(ClosedModel):
    id: UUID
    account_id: UUID
    current_version: int = Field(ge=1)
    created_at: AwareDatetime
    completed_at: AwareDatetime | None


class OperatorGoalsResponse(ClosedModel):
    account_id: UUID
    goals: tuple[OperatorGoalRootResponse, ...] = Field(max_length=OPERATOR_GOAL_PAGE_SIZE)
    next_cursor: str | None
    anchor_created_at: AwareDatetime | None
    anchor_goal_id: UUID | None
    observed_at: AwareDatetime
    pagination: Literal["anchored_search_not_commit_order"] = "anchored_search_not_commit_order"


class OperatorGoalRevisionResponse(ClosedModel):
    goal_id: UUID
    account_id: UUID
    version: int = Field(ge=1)
    subject_id: UUID | None
    subject_label: str = Field(repr=False)
    topic: str | None = Field(repr=False)
    topic_match_key: str | None = Field(repr=False)
    context: str | None = Field(repr=False)
    shared_learning: bool
    saved_at: AwareDatetime
    completed_at: AwareDatetime | None


class OperatorGoalHistoryResponse(ClosedModel):
    goal: OperatorGoalRootResponse
    revisions: tuple[OperatorGoalRevisionResponse, ...] = Field(
        max_length=OPERATOR_GOAL_PAGE_SIZE, repr=False
    )
    next_cursor: str | None
    anchor_version: int = Field(ge=1)
    observed_at: AwareDatetime


def root_response(value: OperatorGoalRoot) -> OperatorGoalRootResponse:
    return OperatorGoalRootResponse(
        id=value.id,
        account_id=value.account_id,
        current_version=value.current_version,
        created_at=value.created_at,
        completed_at=value.completed_at,
    )


def revision_response(value: OperatorGoalRevision) -> OperatorGoalRevisionResponse:
    return OperatorGoalRevisionResponse(
        goal_id=value.goal_id,
        account_id=value.account_id,
        version=value.version,
        subject_id=value.subject_id,
        subject_label=value.subject_label,
        topic=value.topic,
        topic_match_key=value.topic_match_key,
        context=value.context,
        shared_learning=value.shared_learning,
        saved_at=value.saved_at,
        completed_at=value.completed_at,
    )


def goals_response(value: OperatorGoalsPage) -> OperatorGoalsResponse:
    return OperatorGoalsResponse(
        account_id=value.account_id,
        goals=tuple(root_response(row) for row in value.goals),
        next_cursor=value.next_cursor,
        anchor_created_at=value.anchor_created_at,
        anchor_goal_id=value.anchor_goal_id,
        observed_at=value.observed_at,
    )


def goal_history_response(value: OperatorGoalHistoryPage) -> OperatorGoalHistoryResponse:
    return OperatorGoalHistoryResponse(
        goal=root_response(value.goal),
        revisions=tuple(revision_response(row) for row in value.revisions),
        next_cursor=value.next_cursor,
        anchor_version=value.anchor_version,
        observed_at=value.observed_at,
    )
