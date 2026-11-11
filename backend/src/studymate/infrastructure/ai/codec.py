from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from studymate.domain.ai.tasks import (
    AiResult,
    AiTask,
    AssessPhoto,
    ClarifiedGoal,
    ClarifyGoal,
    GoalTextTarget,
    Observation,
    PhotoAssessment,
    Priority,
    ReportTriage,
    SubjectSuggestions,
    SuggestSubject,
    validate_result,
)

TASK_CODEC: TypeAdapter[AiTask] = TypeAdapter(AiTask)
RESULT_CODEC: TypeAdapter[AiResult] = TypeAdapter(AiResult)
MAX_OUTPUT_BYTES = 16_384


class GoalOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    suggestion: str = Field(min_length=1, max_length=240)


class TopicOutput(GoalOutput):
    suggestion: str = Field(min_length=1, max_length=80)


class SubjectOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    ids: tuple[UUID, ...] = Field(max_length=3)


class PhotoOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    blurred: Observation
    face_visible: Observation
    multiple_people: Observation


class TriageOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    priority: Priority
    rationale: str = Field(min_length=1, max_length=240)


def output_model(task: AiTask) -> type[GoalOutput | SubjectOutput | PhotoOutput | TriageOutput]:
    match task:
        case ClarifyGoal():
            return TopicOutput if task.target == GoalTextTarget.TOPIC else GoalOutput
        case SuggestSubject():
            return SubjectOutput
        case AssessPhoto():
            return PhotoOutput
        case _:
            return TriageOutput


def decode_result(task: AiTask, raw: bytes) -> AiResult:
    if len(raw) > MAX_OUTPUT_BYTES:
        raise ValueError("Executor output exceeds limit")
    try:
        parsed = output_model(task).model_validate_json(raw)
    except ValidationError:
        raise ValueError("Executor output does not conform") from None
    match parsed:
        case GoalOutput():
            result: AiResult = ClarifiedGoal(parsed.suggestion)
        case SubjectOutput():
            result = SubjectSuggestions(parsed.ids)
        case PhotoOutput():
            result = PhotoAssessment(parsed.blurred, parsed.face_visible, parsed.multiple_people)
        case TriageOutput():
            result = ReportTriage(parsed.priority, parsed.rationale)
    validate_result(task, result)
    return result


@dataclass(frozen=True, slots=True)
class StoredPayload:
    task: AiTask

    def encode(self) -> str:
        return TASK_CODEC.dump_json(self.task).decode()
