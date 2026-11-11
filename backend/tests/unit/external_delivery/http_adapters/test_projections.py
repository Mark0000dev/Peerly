"""Identified finite metadata and source trust; no fabricated OTP/browser history."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from tests.unit.external_delivery.http_adapters.fixtures import lease, telegram, umami

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
from studymate.domain.external_delivery.delivery import UmamiEvent
from studymate.domain.external_delivery.sources import (
    CanonicalSource,
    CapturedSource,
    CaptureMode,
    ClientObservationSource,
    MembershipEvidence,
    SourceKind,
    SupportCaseSource,
)
from studymate.domain.operator.timeline import OperatorEventFacts, OperatorEventKind
from studymate.domain.support.cases import SupportTopic
from studymate.infrastructure.external_delivery.http_adapters import target_fingerprint
from studymate.infrastructure.external_delivery.http_adapters.projections import umami_payload


def client_events() -> tuple[Observation, ...]:
    header = ObservationHeader(uuid4(), datetime.now(UTC) - timedelta(minutes=1), Screen.STUDY)
    return (
        ScreenViewed(header),
        ActionObserved(header, Action.APPLY, ObservedOutcome.SUCCEEDED),
        PerformanceObserved(header, Metric.LCP, 123.0),
        ErrorObserved(header, ErrorCategory.RENDER, (PublicFrame(1, 5, 7),)),
        HttpObserved(header, HttpMethod.GET, ApiRoute.AI, StatusClass.SUCCESS, 7),
        QualityObserved(header, QualityReason.OVERFLOW, 3),
    )


@pytest.mark.parametrize("event", client_events())
def test_all_client_families_keep_received_time_primary_and_claims_explicit(
    event: Observation,
) -> None:
    job = lease()
    received = datetime.now(UTC)
    source = ClientObservationSource(uuid4(), uuid4(), received, event, "a" * 40)
    captured = CapturedSource(
        job.source_id, SourceKind.CLIENT_OBSERVATION, source, CaptureMode.LIVE, received
    )
    result = umami_payload(replace(job, payload=UmamiEvent(captured)), umami())
    payload = result["payload"]
    assert isinstance(payload, dict)
    assert payload["timestamp"] == int(received.timestamp())
    assert payload["id"] == str(source.actor_id)
    data = payload["data"]
    assert isinstance(data, dict)
    assert data["trust"] == "client_claimed"
    assert data["source_event_id"] == str(source.id)
    assert data["client_event_id"] == str(event.header.event_id)
    assert data["observed_at_untrusted"] == event.header.observed_at.isoformat()
    assert "userAgent" not in payload
    assert "referrer" not in payload


@pytest.mark.parametrize(
    "evidence",
    [
        MembershipEvidence.OTP,
        MembershipEvidence.MANUAL_PLACEHOLDER,
        MembershipEvidence.MANUAL_CHALLENGE,
        MembershipEvidence.UNKNOWN,
    ],
)
def test_manual_or_unknown_membership_never_masquerades_as_otp(
    evidence: MembershipEvidence,
) -> None:
    job = lease()
    original = CanonicalSource(
        uuid4(),
        uuid4(),
        OperatorEventKind.EMAIL_CONFIRMED,
        job.started_at,
        OperatorEventFacts(),
        evidence,
    )
    captured = CapturedSource(
        job.source_id, SourceKind.CANONICAL, original, CaptureMode.BACKFILL_UMAMI, job.started_at
    )
    result = umami_payload(replace(job, payload=UmamiEvent(captured)), umami())
    payload = result["payload"]
    assert isinstance(payload, dict)
    data = payload["data"]
    assert isinstance(data, dict)
    assert data["membership_evidence"] == evidence.value
    if evidence == MembershipEvidence.UNKNOWN:
        assert "otp_consumed" not in data
    else:
        assert data["otp_consumed"] == (evidence == MembershipEvidence.OTP)
    assert data["capture_mode"] == "backfill_umami"


def test_anonymous_support_does_not_invent_actor_identity() -> None:
    job = lease()
    source = SupportCaseSource(uuid4(), None, SupportTopic.CODE_NOT_ARRIVING, job.started_at)
    captured = CapturedSource(
        job.source_id, SourceKind.SUPPORT_CASE, source, CaptureMode.LIVE, job.started_at
    )
    result = umami_payload(replace(job, payload=UmamiEvent(captured)), umami())
    payload = result["payload"]
    assert isinstance(payload, dict)
    assert "id" not in payload
    data = payload["data"]
    assert isinstance(data, dict)
    assert "actor_id" not in data


@pytest.mark.parametrize(
    "origin",
    [
        "http://example.test",
        "https://x.test/",
        "https://u:p@x.test",
        "https://x.test?q=1",
        "https://x.test#f",
        "https://x.test\\evil",
    ],
)
def test_untrusted_origins_cannot_become_destination_or_operator_links(origin: str) -> None:
    with pytest.raises(ValueError, match="HTTPS origin"):
        replace(umami(), origin=origin)
    with pytest.raises(ValueError, match="HTTPS origin"):
        replace(telegram(), operator_origin=origin)


def test_umami_target_identity_is_website_and_origin_not_delivery_revision() -> None:
    config = umami()
    assert target_fingerprint(config) != target_fingerprint(replace(config, website_id=uuid4()))
    assert target_fingerprint(config) != target_fingerprint(
        replace(config, origin="https://other.example.test")
    )
    assert target_fingerprint(config) == target_fingerprint(
        replace(config, destination=replace(config.destination, revision=2))
    )
