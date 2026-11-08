from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from studymate.application.ai.ports import AiJobNotFoundError, DraftSourceIntent, StudentSubmission
from studymate.domain.ai.jobs import AiJob, Failure, JobState
from studymate.domain.ai.tasks import (
    AiKind,
    AssessPhoto,
    ClarifiedGoal,
    ClarifyGoal,
    DraftSnapshotSource,
    GoalTextTarget,
    Observation,
    PhotoAssessment,
    Source,
    SubjectSuggestions,
    TriageReport,
)
from studymate.domain.study_context import MAX_CONTEXT_LENGTH, MAX_TOPIC_LENGTH

POLL_AFTER_MS = 1000


class ResourceSourceRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["resource"]
    id: UUID
    version: int = Field(strict=True, ge=1)

    def source(self) -> Source:
        return Source(self.id, self.version)


class DraftSourceRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["draft"]
    id: UUID
    version: int = Field(strict=True, ge=1)

    def source(self) -> DraftSourceIntent:
        return DraftSourceIntent(self.id, self.version)


SourceRequest = Annotated[ResourceSourceRequest | DraftSourceRequest, Field(discriminator="kind")]


class ClarifyRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["clarify_goal"]
    source: SourceRequest
    target: GoalTextTarget = GoalTextTarget.CONTEXT
    text: str = Field(min_length=1, max_length=MAX_CONTEXT_LENGTH, repr=False)

    def submission(self) -> StudentSubmission:
        return StudentSubmission(
            AiKind.CLARIFY_GOAL, self.source.source(), self.text, target=self.target
        )

    @model_validator(mode="after")
    def validate_submission(self) -> Self:
        self.submission()
        return self


class SuggestRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["suggest_subject"]
    source: SourceRequest
    candidate_ids: tuple[UUID, ...] = Field(min_length=1, max_length=20)
    label: str | None = Field(default=None, min_length=1, max_length=MAX_TOPIC_LENGTH, repr=False)

    def submission(self) -> StudentSubmission:
        return StudentSubmission(
            AiKind.SUGGEST_SUBJECT,
            self.source.source(),
            candidate_ids=self.candidate_ids,
            label=self.label,
        )

    @model_validator(mode="after")
    def validate_submission(self) -> Self:
        self.submission()
        return self


class PhotoRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["assess_photo"]
    source: ResourceSourceRequest

    def submission(self) -> StudentSubmission:
        return StudentSubmission(AiKind.ASSESS_PHOTO, self.source.source())


CreateJobRequest = Annotated[
    ClarifyRequest | SuggestRequest | PhotoRequest, Field(discriminator="kind")
]


class ResourceSourceResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["resource"] = "resource"
    id: UUID
    version: int


class DraftSourceResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["draft"] = "draft"
    id: UUID
    version: int
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ClarifyResultResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    suggestion: str = Field(min_length=1, max_length=MAX_CONTEXT_LENGTH, repr=False)


class SubjectResultResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    ids: tuple[UUID, ...] = Field(max_length=3)


class PhotoResultResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    blurred: Observation
    face_visible: Observation
    multiple_people: Observation


class JobResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID
    kind: Literal["clarify_goal", "suggest_subject", "assess_photo"]
    source: Annotated[ResourceSourceResponse | DraftSourceResponse, Field(discriminator="kind")]
    target: GoalTextTarget | None
    state: JobState
    created_at: datetime
    deadline: datetime
    result: ClarifyResultResponse | SubjectResultResponse | PhotoResultResponse | None = Field(
        repr=False
    )
    failure: Failure | None
    poll_after_ms: int | None


def job_response(job: AiJob) -> JobResponse:
    if isinstance(job.task, TriageReport):
        raise AiJobNotFoundError
    source = job.task.source
    reference = (
        DraftSourceResponse(id=source.id, version=source.version, content_hash=source.content_hash)
        if isinstance(source, DraftSnapshotSource)
        else ResourceSourceResponse(id=source.id, version=source.version)
    )
    result: ClarifyResultResponse | SubjectResultResponse | PhotoResultResponse | None = None
    match job.result:
        case ClarifiedGoal():
            result = ClarifyResultResponse(suggestion=job.result.suggestion)
        case SubjectSuggestions():
            result = SubjectResultResponse(ids=job.result.ids)
        case PhotoAssessment():
            result = PhotoResultResponse(
                blurred=job.result.blurred,
                face_visible=job.result.face_visible,
                multiple_people=job.result.multiple_people,
            )
    kind: Literal["clarify_goal", "suggest_subject", "assess_photo"]
    if isinstance(job.task, ClarifyGoal):
        kind = "clarify_goal"
    elif isinstance(job.task, AssessPhoto):
        kind = "assess_photo"
    else:
        kind = "suggest_subject"
    return JobResponse(
        id=job.id,
        kind=kind,
        source=reference,
        target=job.task.target if isinstance(job.task, ClarifyGoal) else None,
        state=job.state,
        created_at=job.created_at,
        deadline=job.deadline,
        result=result,
        failure=job.failure if job.state in {JobState.FAILED, JobState.EXPIRED} else None,
        poll_after_ms=POLL_AFTER_MS if job.pending else None,
    )
