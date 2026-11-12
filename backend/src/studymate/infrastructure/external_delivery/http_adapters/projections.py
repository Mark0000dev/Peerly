"""Explicit source metadata projections; no dataclass dumps or private content readers."""

from datetime import UTC
from typing import TYPE_CHECKING

from studymate.domain.client_observations.events import (
    ActionObserved,
    ErrorObserved,
    HttpObserved,
    PerformanceObserved,
    ScreenViewed,
)
from studymate.domain.external_delivery.delivery import (
    DeliveryLease,
    SupportTelegramNotice,
    UmamiEvent,
)
from studymate.domain.external_delivery.sources import (
    CanonicalSource,
    ClientObservationSource,
    MembershipEvidence,
    SupportCaseSource,
)
from studymate.domain.operator.timeline import OperatorEventFacts
from studymate.infrastructure.external_delivery.http_adapters.configuration import (
    TelegramConfig,
    UmamiConfig,
)

if TYPE_CHECKING:
    from uuid import UUID


type Json = str | int | float | bool | list[Json] | dict[str, Json] | None


def canonical_facts(facts: OperatorEventFacts) -> dict[str, Json]:
    values: tuple[tuple[str, str | bool | None], ...] = (
        ("topic_present", facts.topic_present),
        ("shared_learning", facts.shared_learning),
        ("onboarding_task", facts.onboarding_task),
        ("ai_kind", facts.ai_kind),
        ("ai_state", facts.ai_state),
        ("ai_reason", facts.ai_reason),
        ("blocked", facts.blocked),
        ("passed", facts.passed),
        ("request_state", facts.request_state),
        ("message_state", facts.message_state),
        ("study_answer", facts.study_answer),
        ("feedback_again", facts.feedback_again),
        ("operator_action", facts.operator_action),
        ("lifecycle_operation", facts.lifecycle_operation),
    )
    return {key: value for key, value in values if value is not None}


def observation_fields(source: ClientObservationSource) -> tuple[str, dict[str, Json]]:
    event = source.event
    data: dict[str, Json] = {
        "client_event_id": str(event.header.event_id),
        "observed_at_untrusted": event.header.observed_at.astimezone(UTC).isoformat(),
        "screen": event.header.screen.value,
    }
    if source.release_id is not None:
        data["release_id"] = source.release_id
    if isinstance(event, ScreenViewed):
        return "client.screen.viewed", data
    if isinstance(event, ActionObserved):
        data.update(action=event.action.value, outcome=event.outcome.value)
        if event.action_id is not None:
            data["action_id"] = str(event.action_id)
        return "client.action.observed", data
    if isinstance(event, PerformanceObserved):
        data.update(metric=event.metric.value, value=event.value)
        return "client.performance.observed", data
    if isinstance(event, ErrorObserved):
        data["category"] = event.category.value
        data["public_frames"] = [
            {"asset_id": frame.asset_id, "line": frame.line, "column": frame.column}
            for frame in event.frames
        ]
        return "client.error.observed", data
    if isinstance(event, HttpObserved):
        data.update(
            method=event.method.value,
            route=event.route.value,
            status_class=event.status_class.value,
            duration_ms=event.duration_ms,
        )
        for key, value in (
            ("request_id", event.request_id),
            ("action_id", event.action_id),
            ("trace_id", event.trace_id),
        ):
            if value is not None:
                data[key] = str(value)
        return "client.http.observed", data
    data.update(reason=event.reason.value, count=event.count)
    return "client.quality.observed", data


def umami_payload(lease: DeliveryLease, configuration: UmamiConfig) -> dict[str, Json]:
    payload = lease.payload
    if not isinstance(payload, UmamiEvent) or payload.source.id != lease.source_id:
        raise ValueError("Umami payload lost its exact captured source")
    captured = payload.source
    source = captured.source
    data: dict[str, Json] = {
        "source_id": str(captured.id),
        "source_event_id": str(source.id),
        "delivery_id": str(lease.delivery_id),
        "source_kind": captured.kind.value,
        "capture_mode": captured.mode.value,
        "routing_version": captured.routing_version,
        "projection_version": lease.projection_version,
    }
    actor: UUID | None
    if isinstance(source, CanonicalSource):
        name, at, actor = "server." + source.kind.value, source.occurred_at, source.actor_id
        data.update(canonical_facts(source.facts))
        data["trust"] = "server_committed"
        if source.membership_evidence != MembershipEvidence.NOT_APPLICABLE:
            data["membership_evidence"] = source.membership_evidence.value
            if source.membership_evidence != MembershipEvidence.UNKNOWN:
                data["otp_consumed"] = source.membership_evidence == MembershipEvidence.OTP
        if source.notification_mode is not None:
            data["notification_mode"] = source.notification_mode.value
        url = "/peerly/server"
    elif isinstance(source, ClientObservationSource):
        name, fields = observation_fields(source)
        data.update(fields)
        data["trust"] = "client_claimed"
        at, actor = source.received_at, source.actor_id
        url = "/peerly/client/" + source.event.header.screen.value
    else:
        name, at, actor = "server.support.received", source.received_at, source.actor_id
        data.update(trust="server_support_receipt", topic=source.topic.value)
        url = "/peerly/server"
    data["source_time"] = at.astimezone(UTC).isoformat()
    result: dict[str, Json] = {
        "website": str(configuration.website_id),
        "name": name,
        "data": data,
        "url": url,
        "timestamp": int(at.timestamp()),
    }
    if actor is not None:
        result["id"] = str(actor)
        data["actor_id"] = str(actor)
    return {"type": "event", "payload": result}


def telegram_payload(lease: DeliveryLease, configuration: TelegramConfig) -> dict[str, Json]:
    if not isinstance(lease.payload, SupportTelegramNotice):
        raise ValueError("Support Telegram requires its exact notice")
    source: SupportCaseSource = lease.payload.source
    body: dict[str, Json] = {
        "chat_id": configuration.chat_id,
        "text": "Peerly support case\nCase: "
        + str(source.id)
        + "\nTopic: "
        + source.topic.value
        + "\nReceived: "
        + source.received_at.astimezone(UTC).isoformat()
        + "\nOpen: "
        + configuration.operator_origin
        + "/operator/support?case="
        + str(source.id),
        "link_preview_options": {"is_disabled": True},
    }
    if configuration.topic_id is not None:
        body["message_thread_id"] = configuration.topic_id
    return body
