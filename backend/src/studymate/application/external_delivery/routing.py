"""Versioned business routing in application code, never inside capture triggers."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from studymate.domain.external_delivery.delivery import (
    DeliveryPayload,
    SupportTelegramNotice,
    UmamiEvent,
)
from studymate.domain.external_delivery.sources import (
    CanonicalSource,
    CapturedSource,
    CaptureMode,
    ClientObservationSource,
    Sink,
)

MATERIALIZATION_BATCH = 50


class ExclusionReason(StrEnum):
    NONE = "none"
    BACKFILL_NOT_ANALYTICS = "backfill_not_analytics"


@dataclass(frozen=True, slots=True)
class DeliveryTarget:
    sink: Sink
    payload: DeliveryPayload


@dataclass(frozen=True, slots=True)
class RoutePlan:
    source_id: UUID
    targets: tuple[DeliveryTarget, ...]
    exclusion_reason: ExclusionReason = ExclusionReason.NONE
    routing_version: int = 1

    def __post_init__(self) -> None:
        if self.routing_version != 1 or len({target.sink for target in self.targets}) != len(
            self.targets
        ):
            raise ValueError(
                "External routing plan requires one destination per versioned source sink"
            )
        if bool(self.targets) != (self.exclusion_reason == ExclusionReason.NONE):
            raise ValueError("Zero-route capture must retain its actual finite exclusion reason")


def route_source(source: CapturedSource) -> RoutePlan:
    fact = source.source
    if source.mode == CaptureMode.BACKFILL_UMAMI:
        if isinstance(fact, (CanonicalSource, ClientObservationSource)) or (fact.actor_id is None):
            return RoutePlan(source.id, (DeliveryTarget(Sink.UMAMI, UmamiEvent(source)),))
        return RoutePlan(source.id, (), ExclusionReason.BACKFILL_NOT_ANALYTICS)
    if isinstance(fact, (CanonicalSource, ClientObservationSource)):
        return RoutePlan(source.id, (DeliveryTarget(Sink.UMAMI, UmamiEvent(source)),))
    # The closed union now narrows to the actual support-case source.
    support = DeliveryTarget(Sink.TELEGRAM_SUPPORT, SupportTelegramNotice(fact))
    targets = (
        (DeliveryTarget(Sink.UMAMI, UmamiEvent(source)), support)
        if fact.actor_id is None
        else (support,)
    )
    return RoutePlan(source.id, targets)


class MaterializationTransaction(Protocol):
    async def sources(self, limit: int) -> tuple[CapturedSource, ...]: ...

    async def materialize(self, plan: RoutePlan) -> None: ...


class MaterializationUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[MaterializationTransaction]: ...


@dataclass(frozen=True, slots=True)
class MaterializeDeliverySources:
    unit_of_work: MaterializationUnitOfWork

    async def __call__(self) -> int:
        async with self.unit_of_work.transaction() as transaction:
            sources = await transaction.sources(MATERIALIZATION_BATCH)
            if len(sources) > MATERIALIZATION_BATCH or len(
                {source.id for source in sources}
            ) != len(sources):
                raise RuntimeError("External source capture exceeded its bounded actual source set")
            for source in sources:
                await transaction.materialize(route_source(source))
            return len(sources)
