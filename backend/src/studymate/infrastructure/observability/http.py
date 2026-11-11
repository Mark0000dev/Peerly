import logging
from dataclasses import dataclass, field

from studymate.application.ports.http_observer import HttpObservation
from studymate.infrastructure.observability.logging import LogEvent
from studymate.infrastructure.observability.tracing import current_execution


@dataclass(frozen=True, slots=True)
class JsonHttpObserver:
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("studymate.http"))

    def completed(self, observation: HttpObservation) -> None:
        execution = current_execution()
        self.logger.info(
            LogEvent.REQUEST_COMPLETED,
            extra={
                "event": LogEvent.REQUEST_COMPLETED,
                "observation": observation,
                "request_id": observation.request_id,
                "action_id": observation.action_id,
                "status": observation.status,
                "duration_seconds": observation.duration_seconds,
                "trace_id": execution.trace_id if execution is not None else None,
                "span_id": execution.span_id if execution is not None else None,
                "account_id": execution.account_id if execution is not None else None,
            },
        )
