from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from studymate.application.ports.http_observer import HttpObservation, RequestMethod


@dataclass(frozen=True, slots=True)
class HttpExecution:
    request_id: UUID
    action_id: UUID | None
    method: RequestMethod
    traceparent: str | None


class HttpSpan(Protocol):
    @property
    def trace_id(self) -> str | None: ...

    def completed(self, observation: HttpObservation) -> None: ...


class HttpTracing(Protocol):
    def start(self, execution: HttpExecution) -> AbstractContextManager[HttpSpan]: ...
