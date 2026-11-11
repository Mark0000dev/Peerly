"""Synthetic exact destination leases, with no database or real provider authority."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from studymate.domain.external_delivery.delivery import (
    DeliveryLease,
    DestinationRef,
    SupportTelegramNotice,
    UmamiEvent,
)
from studymate.domain.external_delivery.sources import (
    CanonicalSource,
    CapturedSource,
    CaptureMode,
    Sink,
    SourceKind,
    SupportCaseSource,
)
from studymate.domain.operator.timeline import OperatorEventFacts, OperatorEventKind
from studymate.domain.support.cases import SupportTopic
from studymate.infrastructure.external_delivery.http_adapters import TelegramConfig, UmamiConfig

TOKEN = "123456:synthetic_PRIVATE_TOKEN"  # noqa: S105 - synthetic marker, no provider authority.


def umami() -> UmamiConfig:
    return UmamiConfig(DestinationRef(Sink.UMAMI, 1), "https://analytics.example.test", uuid4())


def telegram() -> TelegramConfig:
    return TelegramConfig(
        DestinationRef(Sink.TELEGRAM_SUPPORT, 1),
        -100123456,
        "https://console.example.test",
        TOKEN,
        7,
    )


def lease(sink: Sink = Sink.UMAMI) -> DeliveryLease:
    at = datetime.now(UTC)
    if sink == Sink.UMAMI:
        source = CanonicalSource(
            uuid4(),
            uuid4(),
            OperatorEventKind.GOAL_SAVED,
            at,
            OperatorEventFacts(topic_present=True),
        )
        captured = CapturedSource(uuid4(), SourceKind.CANONICAL, source, CaptureMode.LIVE, at)
        payload: UmamiEvent | SupportTelegramNotice = UmamiEvent(captured)
        source_id = captured.id
    else:
        support = SupportCaseSource(uuid4(), uuid4(), next(iter(SupportTopic)), at)
        payload = SupportTelegramNotice(support)
        source_id = uuid4()
    return DeliveryLease(
        uuid4(),
        source_id,
        DestinationRef(sink, 1),
        uuid4(),
        1,
        at,
        at + timedelta(seconds=30),
        payload,
    )
