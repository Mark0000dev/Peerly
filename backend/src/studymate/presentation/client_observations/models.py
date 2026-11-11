from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    field_validator,
    model_validator,
)

from studymate.domain.client_observations.catalogue import (
    Action,
    ApiRoute,
    ErrorCategory,
    HttpMethod,
    Metric,
    ObservedOutcome,
    QualityReason,
    Screen,
    StatusClass,
)
from studymate.domain.client_observations.events import (
    ActionObserved,
    ErrorObserved,
    HttpObserved,
    Observation,
    ObservationHeader,
    PerformanceObserved,
    PublicFrame,
    QualityObserved,
    ScreenViewed,
)


class HeaderBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    event_id: UUID
    observed_at: AwareDatetime
    screen: Screen

    def header(self) -> ObservationHeader:
        return ObservationHeader(self.event_id, self.observed_at, self.screen)


class ScreenViewedBody(HeaderBody):
    kind: Literal["screen.viewed"]

    def event(self) -> ScreenViewed:
        return ScreenViewed(self.header())


class ActionObservedBody(HeaderBody):
    kind: Literal["action.observed"]
    action: Action
    outcome: ObservedOutcome
    action_id: UUID | None = None

    def event(self) -> ActionObserved:
        return ActionObserved(self.header(), self.action, self.outcome, self.action_id)


class PerformanceObservedBody(HeaderBody):
    kind: Literal["performance.observed"]
    metric: Metric
    value: FiniteFloat = Field(ge=0, le=60000, strict=True)

    @model_validator(mode="after")
    def semantic_metric(self) -> "PerformanceObservedBody":
        self.event()
        return self

    def event(self) -> PerformanceObserved:
        return PerformanceObserved(self.header(), self.metric, self.value)


class PublicFrameBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    asset_id: int = Field(ge=0, le=4095, strict=True)
    line: int = Field(ge=1, le=2147483647, strict=True)
    column: int = Field(ge=0, le=2147483647, strict=True)

    def frame(self) -> PublicFrame:
        return PublicFrame(self.asset_id, self.line, self.column)


class ErrorObservedBody(HeaderBody):
    kind: Literal["error.observed"]
    category: ErrorCategory
    frames: tuple[PublicFrameBody, ...] = Field(default=(), max_length=3)

    def event(self) -> ErrorObserved:
        return ErrorObserved(
            self.header(), self.category, tuple(frame.frame() for frame in self.frames)
        )


class HttpObservedBody(HeaderBody):
    kind: Literal["http.observed"]
    method: HttpMethod
    route: ApiRoute
    status_class: StatusClass
    duration_ms: int = Field(ge=0, le=60000, strict=True)
    request_id: UUID | None = None
    action_id: UUID | None = None
    trace_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")

    @model_validator(mode="after")
    def semantic_trace(self) -> "HttpObservedBody":
        self.event()
        return self

    def event(self) -> HttpObserved:
        return HttpObserved(
            self.header(),
            self.method,
            self.route,
            self.status_class,
            self.duration_ms,
            self.request_id,
            self.action_id,
            self.trace_id,
        )


class QualityObservedBody(HeaderBody):
    kind: Literal["quality.observed"]
    reason: QualityReason
    count: int = Field(ge=1, le=65535, strict=True)

    def event(self) -> QualityObserved:
        return QualityObserved(self.header(), self.reason, self.count)


type ObservationBody = Annotated[
    ScreenViewedBody
    | ActionObservedBody
    | PerformanceObservedBody
    | ErrorObservedBody
    | HttpObservedBody
    | QualityObservedBody,
    Field(discriminator="kind"),
]


class ObservationBatchBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1]
    expected_actor_id: UUID | None = None
    release_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    events: tuple[ObservationBody, ...] = Field(min_length=1, max_length=20)

    @field_validator("schema_version", mode="before")
    @classmethod
    def strict_version(cls, value: object) -> object:
        if type(value) is not int or value != 1:
            raise ValueError("Observation schema requires integer version1")
        return value

    @model_validator(mode="after")
    def distinct_events_and_frame_release(self) -> "ObservationBatchBody":
        if len({event.event_id for event in self.events}) != len(self.events):
            raise ValueError("Observation batch repeats an event identifier")
        if self.release_id is None and any(
            isinstance(event, ErrorObservedBody) and event.frames for event in self.events
        ):
            raise ValueError("Observed public frames require their release identity")
        return self

    def observations(self) -> tuple[Observation, ...]:
        return tuple(event.event() for event in self.events)


class ObservationBatchResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    accepted: tuple[UUID, ...] = Field(max_length=20)
    duplicates: tuple[UUID, ...] = Field(max_length=20)
    received_at: AwareDatetime
