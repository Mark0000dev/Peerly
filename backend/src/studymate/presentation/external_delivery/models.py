"""Closed operator metadata DTOs; no provider credentials or stored private content."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from studymate.domain.external_delivery.inspection import DeliverySummary, SourceSummary
from studymate.domain.external_delivery.sources import CapturedSource, SourceKind


class SourceQuery(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    actor_id: UUID | None = None
    kind: SourceKind | None = None
    cursor: str | None = Field(default=None, min_length=1, max_length=1024)


class SourcesResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    sources: tuple[SourceSummary, ...] = Field(max_length=50)
    next_cursor: str | None


class SourceDetailResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", from_attributes=True)
    summary: SourceSummary
    source: CapturedSource
    deliveries: tuple[DeliverySummary, ...] = Field(max_length=2)
