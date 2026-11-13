"""Explicit maintenance recovery of one blocked sink, never delivery replay."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from studymate.domain.time import require_aware

FINGERPRINT_BYTES = 32
PLAN_LIFETIME = timedelta(minutes=5)


class RecoveryRejectedError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class UmamiRecoveryTarget:
    revision: int
    fingerprint: bytes
    failed_delivery_id: UUID

    def __post_init__(self) -> None:
        if (
            isinstance(self.revision, bool)
            or self.revision < 1
            or len(self.fingerprint) != FINGERPRINT_BYTES
        ):
            raise RecoveryRejectedError("invalid_recovery_target")


@dataclass(frozen=True, slots=True)
class UmamiRecoveryState:
    observed_at: datetime
    registered_at: datetime
    turn: int
    next_claim_at: datetime
    cooldown_until: datetime | None
    blocked_reason: str | None
    failed_source_id: UUID
    attempt_no: int
    lease_id: UUID
    started_at: datetime
    ended_at: datetime
    delivery_updated_at: datetime

    def __post_init__(self) -> None:
        for value in (
            self.observed_at,
            self.registered_at,
            self.next_claim_at,
            self.started_at,
            self.ended_at,
            self.delivery_updated_at,
        ):
            require_aware(value)
        if self.cooldown_until is not None:
            require_aware(self.cooldown_until)

    def comparison(self) -> tuple[object, ...]:
        return (
            self.registered_at,
            self.turn,
            self.next_claim_at,
            self.cooldown_until,
            self.blocked_reason,
            self.failed_source_id,
            self.attempt_no,
            self.lease_id,
            self.started_at,
            self.ended_at,
            self.delivery_updated_at,
        )


class UmamiRecoveryTransaction(Protocol):
    async def inspect(self, target: UmamiRecoveryTarget, *, lock: bool) -> UmamiRecoveryState: ...
    async def clear_block(self, expected: UmamiRecoveryState) -> bool: ...


async def recover_umami_sink(
    transaction: UmamiRecoveryTransaction,
    target: UmamiRecoveryTarget,
    approved: UmamiRecoveryState,
) -> UmamiRecoveryState:
    """Caller owns commit; no provider, registration, counter or delivery mutation."""
    actual = await transaction.inspect(target, lock=True)
    if not timedelta(0) <= actual.observed_at - approved.observed_at <= PLAN_LIFETIME:
        raise RecoveryRejectedError("stale_or_future_recovery_plan")
    if actual.comparison() != approved.comparison():
        raise RecoveryRejectedError("recovery_snapshot_changed")
    if actual.blocked_reason != "destination_unavailable":
        raise RecoveryRejectedError("sink_not_destination_blocked")
    if not await transaction.clear_block(actual):
        raise RecoveryRejectedError("recovery_compare_and_swap_failed")
    return actual
