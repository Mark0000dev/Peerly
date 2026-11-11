"""Closed ORM-to-domain decoding; frame rows are loaded explicitly in one batch."""

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
from studymate.infrastructure.client_observations.models import ClientObservationRecord


def read_observation(row: ClientObservationRecord, frames: tuple[PublicFrame, ...]) -> Observation:
    header = ObservationHeader(row.event_id, row.observed_at, Screen(row.screen))
    if (
        row.kind == "quality.observed"
        and row.quality_reason is not None
        and row.quality_count is not None
    ):
        return QualityObserved(header, QualityReason(row.quality_reason), row.quality_count)
    if row.kind == "screen.viewed":
        return ScreenViewed(header)
    if row.kind == "action.observed" and row.action is not None and row.outcome is not None:
        return ActionObserved(
            header, Action(row.action), ObservedOutcome(row.outcome), row.action_id
        )
    if row.kind == "performance.observed" and row.metric is not None and row.value is not None:
        return PerformanceObserved(header, Metric(row.metric), row.value)
    if row.kind == "error.observed" and row.category is not None:
        return ErrorObserved(header, ErrorCategory(row.category), frames)
    if (
        row.kind == "http.observed"
        and row.method is not None
        and row.route is not None
        and row.status_class is not None
        and row.duration_ms is not None
    ):
        return HttpObserved(
            header,
            HttpMethod(row.method),
            ApiRoute(row.route),
            StatusClass(row.status_class),
            row.duration_ms,
            row.request_id,
            row.action_id,
            row.trace_id,
        )
    raise RuntimeError("Stored client observation lost its closed actual source shape")
