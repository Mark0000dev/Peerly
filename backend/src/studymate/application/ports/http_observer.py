"""Content-free HTTP execution metadata; no web or observability SDK dependency."""

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

RequestMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "OTHER"]
CLIENT_CANCELLED_STATUS = 499


@dataclass(frozen=True, slots=True)
class HttpObservation:
    request_id: UUID
    action_id: UUID | None
    method: RequestMethod
    route: str | None
    status: int
    duration_seconds: float


class HttpObserver(Protocol):
    def completed(self, observation: HttpObservation) -> None: ...
