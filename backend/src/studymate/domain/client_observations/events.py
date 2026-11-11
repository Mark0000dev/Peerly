"""Immutable bounded client observations, never server source evidence."""

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

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
from studymate.domain.time import require_aware

MAX_EVENTS = 20
MAX_FRAMES = 3
MAX_ASSET_ID = 4095
MAX_COORDINATE = (1 << 31) - 1
MAX_MILLISECONDS = 60000
MAX_CLS = 100


def bounded_integer(value: int, low: int, high: int) -> None:
    if isinstance(value, bool) or not low <= value <= high:
        raise ValueError("Observation integer is outside its semantic bounds")


@dataclass(frozen=True, slots=True)
class ObservationHeader:
    event_id: UUID
    observed_at: datetime
    screen: Screen

    def __post_init__(self) -> None:
        require_aware(self.observed_at)

    def parts(self) -> tuple[str, ...]:
        return (str(self.event_id), self.observed_at.astimezone(UTC).isoformat(), self.screen.value)


@dataclass(frozen=True, slots=True)
class PublicFrame:
    asset_id: int
    line: int
    column: int

    def __post_init__(self) -> None:
        bounded_integer(self.asset_id, 0, MAX_ASSET_ID)
        bounded_integer(self.line, 1, MAX_COORDINATE)
        bounded_integer(self.column, 0, MAX_COORDINATE)

    def parts(self) -> tuple[str, ...]:
        return (str(self.asset_id), str(self.line), str(self.column))


@dataclass(frozen=True, slots=True)
class ScreenViewed:
    header: ObservationHeader

    def parts(self) -> tuple[str, ...]:
        return ("screen.viewed", *self.header.parts())


@dataclass(frozen=True, slots=True)
class ActionObserved:
    header: ObservationHeader
    action: Action
    outcome: ObservedOutcome
    action_id: UUID | None = None

    def parts(self) -> tuple[str, ...]:
        return (
            "action.observed",
            *self.header.parts(),
            self.action.value,
            self.outcome.value,
            str(self.action_id or ""),
        )


@dataclass(frozen=True, slots=True)
class PerformanceObserved:
    header: ObservationHeader
    metric: Metric
    value: float

    def __post_init__(self) -> None:
        upper = MAX_CLS if self.metric == Metric.CLS else MAX_MILLISECONDS
        if (
            isinstance(self.value, bool)
            or not math.isfinite(self.value)
            or not 0 <= self.value <= upper
        ):
            raise ValueError("Observed metric is outside its finite semantic bounds")

    def parts(self) -> tuple[str, ...]:
        return (
            "performance.observed",
            *self.header.parts(),
            self.metric.value,
            repr(float(self.value)),
        )


@dataclass(frozen=True, slots=True)
class ErrorObserved:
    header: ObservationHeader
    category: ErrorCategory
    frames: tuple[PublicFrame, ...] = ()

    def __post_init__(self) -> None:
        if len(self.frames) > MAX_FRAMES:
            raise ValueError("Observed error exceeds its public frame bound")

    def parts(self) -> tuple[str, ...]:
        return (
            "error.observed",
            *self.header.parts(),
            self.category.value,
            str(len(self.frames)),
            *(part for frame in self.frames for part in frame.parts()),
        )


@dataclass(frozen=True, slots=True)
class HttpObserved:
    header: ObservationHeader
    method: HttpMethod
    route: ApiRoute
    status_class: StatusClass
    duration_ms: int
    request_id: UUID | None = None
    action_id: UUID | None = None
    trace_id: str | None = None

    def __post_init__(self) -> None:
        bounded_integer(self.duration_ms, 0, MAX_MILLISECONDS)
        if self.trace_id is not None and (
            re.fullmatch(r"[0-9a-f]{32}", self.trace_id) is None or self.trace_id == "0" * 32
        ):
            raise ValueError("Observed trace link requires a valid nonzero identifier")

    def parts(self) -> tuple[str, ...]:
        return (
            "http.observed",
            *self.header.parts(),
            self.method.value,
            self.route.value,
            self.status_class.value,
            str(self.duration_ms),
            str(self.request_id or ""),
            str(self.action_id or ""),
            self.trace_id or "",
        )


MAX_QUALITY_COUNT = 65535


@dataclass(frozen=True, slots=True)
class QualityObserved:
    """Client-claimed discarded/unconfirmed records, never proven delivery loss."""

    header: ObservationHeader
    reason: QualityReason
    count: int

    def __post_init__(self) -> None:
        bounded_integer(self.count, 1, MAX_QUALITY_COUNT)

    def parts(self) -> tuple[str, ...]:
        return ("quality.observed", *self.header.parts(), self.reason.value, str(self.count))


type Observation = (
    ScreenViewed
    | ActionObserved
    | PerformanceObserved
    | ErrorObserved
    | HttpObserved
    | QualityObserved
)
