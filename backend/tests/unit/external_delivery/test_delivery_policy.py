"""Routing truth and bounded recovery definitions; no provider/database calls."""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from studymate.application.external_delivery.membership import membership_evidence
from studymate.application.external_delivery.routing import ExclusionReason, route_source
from studymate.application.external_delivery.worker import (
    LEASE_SECONDS,
    DeliverNextExternalEvent,
    plan_completion,
)
from studymate.domain.external_delivery.delivery import (
    DeliveryLease,
    DeliveryResult,
    DeliveryState,
    DestinationRef,
    FailureCode,
    ResultKind,
    SupportTelegramNotice,
)
from studymate.domain.external_delivery.sources import (
    CapturedSource,
    CaptureMode,
    MembershipEvidence,
    Sink,
    SourceKind,
    SupportCaseSource,
)
from studymate.domain.support.cases import SupportTopic

NOW = datetime(2026, 11, 10, tzinfo=UTC)


@pytest.mark.parametrize("authenticated", [False, True])
def test_support_routes_actual_creation_without_double_counting(authenticated: bool) -> None:
    case = SupportCaseSource(uuid4(), uuid4() if authenticated else None, SupportTopic.OTHER, NOW)
    source = CapturedSource(uuid4(), SourceKind.SUPPORT_CASE, case, CaptureMode.LIVE, NOW)
    sinks = tuple(target.sink for target in route_source(source).targets)
    assert sinks == (
        (Sink.TELEGRAM_SUPPORT,) if authenticated else (Sink.UMAMI, Sink.TELEGRAM_SUPPORT)
    )
    backfill = CapturedSource(source.id, source.kind, case, CaptureMode.BACKFILL_UMAMI, NOW)
    assert all(target.sink == Sink.UMAMI for target in route_source(backfill).targets)
    assert route_source(backfill).exclusion_reason == (
        ExclusionReason.BACKFILL_NOT_ANALYTICS if authenticated else ExclusionReason.NONE
    )


@pytest.mark.parametrize("proof", [False, True])
def test_manual_membership_never_claims_otp_even_with_consumed_challenge(proof: bool) -> None:
    operation = "a" * 32
    assert (
        membership_evidence(f"smv1:{operation}:p:operator", consumed_challenge_proven=proof)
        == MembershipEvidence.MANUAL_PLACEHOLDER
    )
    assert (
        membership_evidence(
            f"smv1:{operation}:c{'b' * 22}:operator", consumed_challenge_proven=proof
        )
        == MembershipEvidence.MANUAL_CHALLENGE
    )
    assert membership_evidence("institutional_binding", consumed_challenge_proven=proof) == (
        MembershipEvidence.OTP if proof else MembershipEvidence.UNKNOWN
    )
    assert (
        membership_evidence("legacy", consumed_challenge_proven=proof) == MembershipEvidence.UNKNOWN
    )


def test_rate_limit_persists_provider_cooldown_and_caps_attempts() -> None:
    result = DeliveryResult(ResultKind.RETRYABLE, FailureCode.RATE_LIMITED, 429, 7200)
    retry = plan_completion(1, result, NOW)
    assert retry.state == DeliveryState.RETRY
    assert retry.next_attempt_at == retry.cooldown_until == NOW + timedelta(hours=2)
    assert plan_completion(8, result, NOW).state == DeliveryState.DEAD
    excessive = DeliveryResult(ResultKind.RETRYABLE, FailureCode.RATE_LIMITED, 429, 604801)
    assert plan_completion(1, excessive, NOW).block_sink
    credentials = DeliveryResult(ResultKind.PERMANENT, FailureCode.CREDENTIALS, 401)
    assert plan_completion(1, credentials, NOW).block_sink


@dataclass
class WorkerBoundary:
    visited: list[Sink] = field(default_factory=list)
    finished: list[DeliveryResult] = field(default_factory=list)
    cancel: bool = False
    timeout: bool = False
    sending: bool = False

    async def next_sink(self, excluded: frozenset[Sink]) -> Sink | None:
        return next((sink for sink in Sink if sink not in excluded), None)

    def destination(self, sink: Sink) -> DestinationRef | None:
        return None if sink == Sink.UMAMI else DestinationRef(sink, 1)

    async def claim(self, destination: DestinationRef, lease_seconds: int) -> DeliveryLease | None:
        assert not self.sending
        assert lease_seconds == LEASE_SECONDS
        self.visited.append(destination.sink)
        case = SupportCaseSource(uuid4(), None, SupportTopic.OTHER, NOW)
        return DeliveryLease(
            uuid4(),
            uuid4(),
            destination,
            uuid4(),
            1,
            NOW,
            NOW + timedelta(seconds=lease_seconds),
            SupportTelegramNotice(case),
        )

    async def send(self, lease: DeliveryLease) -> DeliveryResult:
        assert lease.destination.sink == Sink.TELEGRAM_SUPPORT
        self.sending = True
        try:
            if self.cancel:
                raise asyncio.CancelledError
            if self.timeout:
                raise TimeoutError
            return DeliveryResult(ResultKind.ACCEPTED, provider_message_id=123)
        finally:
            self.sending = False

    async def finish(self, lease: DeliveryLease, result: DeliveryResult) -> None:
        assert not self.sending
        assert lease.attempt_no == 1
        self.finished.append(result)


async def test_missing_destination_does_not_starve_support_or_consume_attempt() -> None:
    boundary = WorkerBoundary()
    assert await DeliverNextExternalEvent(boundary, boundary, boundary)()
    assert boundary.visited == [Sink.TELEGRAM_SUPPORT]
    assert boundary.finished == [DeliveryResult(ResultKind.ACCEPTED, provider_message_id=123)]


async def test_timeout_is_ambiguous_and_cancellation_leaves_started_lease() -> None:
    boundary = WorkerBoundary(timeout=True)
    assert await DeliverNextExternalEvent(boundary, boundary, boundary)()
    assert boundary.finished == [DeliveryResult(ResultKind.AMBIGUOUS, FailureCode.TIMEOUT)]
    boundary = WorkerBoundary(cancel=True)
    with pytest.raises(asyncio.CancelledError):
        await DeliverNextExternalEvent(boundary, boundary, boundary)()
    assert boundary.finished == []
