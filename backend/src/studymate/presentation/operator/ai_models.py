"""Closed operator projections of retained raw AI business records, never executor authority."""

from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from studymate.application.operator.ai_jobs import OperatorAiJobInspection, OperatorAiJobsPage
from studymate.application.operator.ai_ports import OperatorAiFilters
from studymate.domain.ai.jobs import Failure, JobState
from studymate.domain.ai.tasks import AiKind
from studymate.domain.operator.ai_jobs import (
    OPERATOR_AI_MAX_ATTEMPTS,
    OPERATOR_AI_PAGE_SIZE,
    OperatorAiAttemptOutcome,
    OperatorAiJobMetadata,
)
from studymate.presentation.operator.models import ClosedModel
from studymate.presentation.operator.timeline_models import (
    OperatorEventOriginResponse,
    origin_response,
)


class OperatorAiJobsQuery(ClosedModel):
    kind: AiKind | None = None
    state: JobState | None = None
    created_from: AwareDatetime | None = None
    created_before: AwareDatetime | None = None
    cursor: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)

    def filters(self) -> OperatorAiFilters:
        return OperatorAiFilters(self.kind, self.state, self.created_from, self.created_before)

    @model_validator(mode="after")
    def valid_filters(self) -> Self:
        self.filters()
        return self


class OperatorAiJobQuery(ClosedModel):
    """No execution, role, source-access or representation overrides."""


class OperatorAiVersionsResponse(ClosedModel):
    model: str
    prompt_version: str
    schema_version: str
    adapter: str


class OperatorAiMetadataResponse(ClosedModel):
    id: UUID
    account_id: UUID
    kind: AiKind
    state: JobState
    source_id: UUID
    source_version: int = Field(ge=1)
    created_at: AwareDatetime
    deadline: AwareDatetime
    not_before: AwareDatetime
    attempts_count: int = Field(ge=0, le=OPERATOR_AI_MAX_ATTEMPTS)
    failure: Failure | None
    versions: OperatorAiVersionsResponse
    origin: OperatorEventOriginResponse


class OperatorAiJobsResponse(ClosedModel):
    account_id: UUID
    jobs: tuple[OperatorAiMetadataResponse, ...] = Field(max_length=OPERATOR_AI_PAGE_SIZE)
    next_cursor: str | None
    anchor_created_at: AwareDatetime | None
    anchor_job_id: UUID | None
    observed_at: AwareDatetime
    pagination: Literal["anchored_search_not_commit_order"] = "anchored_search_not_commit_order"


class OperatorAiAttemptResponse(ClosedModel):
    job_id: UUID
    number: int = Field(ge=1, le=OPERATOR_AI_MAX_ATTEMPTS)
    started_at: AwareDatetime
    ended_at: AwareDatetime | None
    outcome: OperatorAiAttemptOutcome | None


class OperatorAiJobResponse(ClosedModel):
    job: OperatorAiMetadataResponse
    input_digest_hex: str = Field(repr=False)
    input_json_raw: str = Field(repr=False)
    result_json_raw: str | None = Field(repr=False)
    representation: Literal["raw_stored_text_not_current_task_schema"] = (
        "raw_stored_text_not_current_task_schema"
    )
    attempts_current: tuple[OperatorAiAttemptResponse, ...] = Field(
        max_length=OPERATOR_AI_MAX_ATTEMPTS
    )
    attempt_observation: Literal["current_recorded_not_job_snapshot"] = (
        "current_recorded_not_job_snapshot"
    )
    observed_at: AwareDatetime


def metadata_response(value: OperatorAiJobMetadata) -> OperatorAiMetadataResponse:
    return OperatorAiMetadataResponse(
        id=value.id,
        account_id=value.account_id,
        kind=value.kind,
        state=value.state,
        source_id=value.source_id,
        source_version=value.source_version,
        created_at=value.created_at,
        deadline=value.deadline,
        not_before=value.not_before,
        attempts_count=value.attempts_count,
        failure=value.failure,
        versions=OperatorAiVersionsResponse(
            model=value.versions.model,
            prompt_version=value.versions.prompt,
            schema_version=value.versions.schema,
            adapter=value.versions.adapter,
        ),
        origin=origin_response(value.origin),
    )


def ai_jobs_response(value: OperatorAiJobsPage) -> OperatorAiJobsResponse:
    return OperatorAiJobsResponse(
        account_id=value.account_id,
        jobs=tuple(metadata_response(row) for row in value.jobs),
        next_cursor=value.next_cursor,
        anchor_created_at=value.anchor_created_at,
        anchor_job_id=value.anchor_job_id,
        observed_at=value.observed_at,
    )


def ai_job_response(value: OperatorAiJobInspection) -> OperatorAiJobResponse:
    detail = value.detail
    return OperatorAiJobResponse(
        job=metadata_response(detail.job),
        input_digest_hex=detail.input_digest.hex(),
        input_json_raw=detail.input_json_raw,
        result_json_raw=detail.result_json_raw,
        attempts_current=tuple(
            OperatorAiAttemptResponse(
                job_id=row.job_id,
                number=row.number,
                started_at=row.started_at,
                ended_at=row.ended_at,
                outcome=row.outcome,
            )
            for row in detail.attempts_current
        ),
        observed_at=value.observed_at,
    )
