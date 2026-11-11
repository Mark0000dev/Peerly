"""Durable correlation metadata, never authentication or private content."""

import re
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ExecutionOrigin:
    request_id: UUID
    action_id: UUID | None
    trace_id: str | None
    span_id: str | None

    def __post_init__(self) -> None:
        if self.trace_id is None and self.span_id is None:
            return
        if (
            self.trace_id is None
            or self.span_id is None
            or re.fullmatch(r"[0-9a-f]{32}", self.trace_id) is None
            or re.fullmatch(r"[0-9a-f]{16}", self.span_id) is None
            or int(self.trace_id, 16) == 0
            or int(self.span_id, 16) == 0
        ):
            raise ValueError("Origin requires a valid trace/span pair")
