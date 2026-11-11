import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal
from uuid import UUID

from studymate.domain.media import MediaObjectRef
from studymate.domain.study_context import MAX_CONTEXT_LENGTH, MAX_TOPIC_LENGTH
from studymate.domain.text import plain_text

MAX_CANDIDATES = 20
MAX_SUGGESTIONS = 3
MAX_EVIDENCE = 4000


class AiKind(StrEnum):
    CLARIFY_GOAL = "clarify_goal"
    SUGGEST_SUBJECT = "suggest_subject"
    ASSESS_PHOTO = "assess_photo"
    TRIAGE_REPORT = "triage_report"


@dataclass(frozen=True, slots=True)
class Source:
    id: UUID
    version: int
    kind: Literal["resource"] = "resource"

    def __post_init__(self) -> None:
        if isinstance(self.version, bool) or self.version < 1:
            raise ValueError("Source revision must be positive")


@dataclass(frozen=True, slots=True)
class DraftSnapshotSource:
    id: UUID
    version: int
    content_hash: str = field(repr=False)
    kind: Literal["draft"] = "draft"

    def __post_init__(self) -> None:
        Source(self.id, self.version)
        if re.fullmatch(r"[0-9a-f]{64}", self.content_hash) is None:
            raise ValueError("Draft snapshot requires an actual bounded content hash")


type GoalAiSource = Source | DraftSnapshotSource


class GoalTextTarget(StrEnum):
    CONTEXT = "context"
    TOPIC = "topic"

    @property
    def maximum(self) -> int:
        return MAX_TOPIC_LENGTH if self == GoalTextTarget.TOPIC else MAX_CONTEXT_LENGTH


@dataclass(frozen=True, slots=True)
class ClarifyGoal:
    source: GoalAiSource
    text: str = field(repr=False)
    target: GoalTextTarget = GoalTextTarget.CONTEXT

    def __post_init__(self) -> None:
        if len(self.text) > self.target.maximum:
            raise ValueError("Goal text exceeds the selected target bound")
        plain_text(
            self.text,
            minimum=1,
            maximum=self.target.maximum,
            multiline=self.target == GoalTextTarget.CONTEXT,
        )


@dataclass(frozen=True, slots=True)
class Candidate:
    id: UUID
    label: str = field(repr=False)

    def __post_init__(self) -> None:
        if len(self.label) > MAX_TOPIC_LENGTH:
            raise ValueError("Subject label exceeds bound")
        plain_text(self.label, minimum=1, maximum=MAX_TOPIC_LENGTH)


@dataclass(frozen=True, slots=True)
class SuggestSubject:
    source: GoalAiSource
    label: str = field(repr=False)
    candidates: tuple[Candidate, ...] = field(repr=False)

    def __post_init__(self) -> None:
        if len(self.label) > MAX_TOPIC_LENGTH:
            raise ValueError("Subject label exceeds bound")
        plain_text(self.label, minimum=1, maximum=MAX_TOPIC_LENGTH)
        if not 1 <= len(self.candidates) <= MAX_CANDIDATES or len(
            {candidate.id for candidate in self.candidates}
        ) != len(self.candidates):
            raise ValueError("Candidates must be distinct and bounded")


@dataclass(frozen=True, slots=True)
class AssessPhoto:
    source: Source
    reference: MediaObjectRef = field(repr=False)


@dataclass(frozen=True, slots=True)
class TriageReport:
    source: Source
    evidence: str = field(repr=False)

    def __post_init__(self) -> None:
        if len(self.evidence) > MAX_EVIDENCE:
            raise ValueError("Selected evidence exceeds bound")
        plain_text(self.evidence, minimum=1, maximum=MAX_EVIDENCE, multiline=True)


type AiTask = ClarifyGoal | SuggestSubject | AssessPhoto | TriageReport


def kind_of(task: AiTask) -> AiKind:
    match task:
        case ClarifyGoal():
            return AiKind.CLARIFY_GOAL
        case SuggestSubject():
            return AiKind.SUGGEST_SUBJECT
        case AssessPhoto():
            return AiKind.ASSESS_PHOTO
        case TriageReport():
            return AiKind.TRIAGE_REPORT


class Observation(StrEnum):
    YES = "yes"
    NO = "no"
    UNCERTAIN = "uncertain"


class Priority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class ClarifiedGoal:
    suggestion: str = field(repr=False)

    def __post_init__(self) -> None:
        if len(self.suggestion) > MAX_CONTEXT_LENGTH:
            raise ValueError("Suggestion exceeds bound")
        plain_text(self.suggestion, minimum=1, maximum=MAX_CONTEXT_LENGTH, multiline=True)


@dataclass(frozen=True, slots=True)
class SubjectSuggestions:
    ids: tuple[UUID, ...]

    def __post_init__(self) -> None:
        if len(self.ids) > MAX_SUGGESTIONS or len(set(self.ids)) != len(self.ids):
            raise ValueError("Suggestions must be distinct and bounded")


@dataclass(frozen=True, slots=True)
class PhotoAssessment:
    blurred: Observation
    face_visible: Observation
    multiple_people: Observation


@dataclass(frozen=True, slots=True)
class ReportTriage:
    priority: Priority
    rationale: str = field(repr=False)

    def __post_init__(self) -> None:
        if len(self.rationale) > MAX_CONTEXT_LENGTH:
            raise ValueError("Rationale exceeds bound")
        plain_text(self.rationale, minimum=1, maximum=MAX_CONTEXT_LENGTH, multiline=True)


type AiResult = ClarifiedGoal | SubjectSuggestions | PhotoAssessment | ReportTriage


def validate_result(task: AiTask, result: AiResult) -> None:
    match task, result:
        case ClarifyGoal(), ClarifiedGoal():
            if len(result.suggestion) <= task.target.maximum:
                return
        case SuggestSubject(), SubjectSuggestions():
            if set(result.ids) <= {candidate.id for candidate in task.candidates}:
                return
        case AssessPhoto(), PhotoAssessment():
            return
        case TriageReport(), ReportTriage():
            return
    raise ValueError("Result does not conform to the submitted task")
