"""Optional transport observation port; no provider SDK or business authority."""

from datetime import datetime
from enum import StrEnum
from typing import Protocol


class StreamEnd(StrEnum):
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    BACKPRESSURE = "backpressure_timeout"
    UNAUTHENTICATED = "unauthenticated"
    DENIED = "denied"
    STORAGE = "storage_unavailable"
    ERROR = "error"


class StreamFrame(StrEnum):
    CHANGE = "change"
    RESET = "reset"
    HEARTBEAT = "heartbeat"


class StreamSend(StrEnum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    ERROR = "error"


class StreamObservation(Protocol):
    def opened(self) -> None: ...
    def closed(self, reason: StreamEnd) -> None: ...
    def frame(self, kind: StreamFrame, published_at: datetime | None = None) -> None: ...
    def sent(self, seconds: float, *, outcome: StreamSend) -> None: ...


class StreamObservations(Protocol):
    def stream(self) -> StreamObservation: ...
