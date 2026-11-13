"""Bound-session maintenance adapter; only the exact schedule block may change."""

from dataclasses import dataclass
from http import HTTPStatus

from sqlalchemy import exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.application.external_delivery.recovery import (
    RecoveryRejectedError,
    UmamiRecoveryState,
    UmamiRecoveryTarget,
)
from studymate.infrastructure.external_delivery.materialization import database_now
from studymate.infrastructure.external_delivery.models import (
    DeliveryAttemptRecord,
    DeliveryDestinationRecord,
    DeliveryScheduleRecord,
    ExternalDeliveryRecord,
)


@dataclass(frozen=True, slots=True)
class SqlUmamiRecoveryTransaction:
    session: AsyncSession

    async def inspect(self, target: UmamiRecoveryTarget, *, lock: bool) -> UmamiRecoveryState:
        schedule_query = select(DeliveryScheduleRecord).where(
            DeliveryScheduleRecord.sink == "umami"
        )
        if lock:
            schedule_query = schedule_query.with_for_update()
        schedule = await self.session.scalar(schedule_query)
        if schedule is None:
            raise RecoveryRejectedError("missing_umami_schedule")
        registry_query = (
            select(DeliveryDestinationRecord)
            .where(DeliveryDestinationRecord.sink == "umami")
            .order_by(DeliveryDestinationRecord.revision.desc())
            .limit(1)
        )
        if lock:
            registry_query = registry_query.with_for_update(read=True)
        registry = await self.session.scalar(registry_query)
        if (
            registry is None
            or registry.revision != target.revision
            or registry.fingerprint != target.fingerprint
        ):
            raise RecoveryRejectedError("current_registry_target_mismatch")
        delivery_query = select(ExternalDeliveryRecord).where(
            ExternalDeliveryRecord.id == target.failed_delivery_id,
            ExternalDeliveryRecord.sink == "umami",
        )
        if lock:
            delivery_query = delivery_query.with_for_update(read=True)
        delivery = await self.session.scalar(delivery_query)
        if (
            delivery is None
            or delivery.state != "dead"
            or delivery.last_failure != "destination_unavailable"
            or delivery.destination_revision != target.revision
            or delivery.lease_id is not None
            or delivery.lease_until is not None
            or delivery.delivered_at is not None
        ):
            raise RecoveryRejectedError("dead_destination_evidence_mismatch")
        attempt_query = select(DeliveryAttemptRecord).where(
            DeliveryAttemptRecord.delivery_id == delivery.id,
            DeliveryAttemptRecord.attempt_no == delivery.attempt_count,
        )
        if lock:
            attempt_query = attempt_query.with_for_update(read=True)
        attempt = await self.session.scalar(attempt_query)
        if (
            attempt is None
            or attempt.ended_at is None
            or attempt.outcome != "permanent"
            or attempt.http_status != HTTPStatus.OK
            or attempt.failure != "destination_unavailable"
            or attempt.late_ack_at is not None
        ):
            raise RecoveryRejectedError("terminal_attempt_evidence_mismatch")
        in_flight = await self.session.scalar(
            select(
                exists().where(
                    ExternalDeliveryRecord.sink == "umami",
                    ExternalDeliveryRecord.state == "leased",
                )
            )
        )
        unresolved = await self.session.scalar(
            select(
                exists().where(
                    DeliveryAttemptRecord.delivery_id == ExternalDeliveryRecord.id,
                    ExternalDeliveryRecord.sink == "umami",
                    DeliveryAttemptRecord.ended_at.is_(None),
                )
            )
        )
        if in_flight or unresolved:
            raise RecoveryRejectedError("umami_attempt_still_in_flight")
        return UmamiRecoveryState(
            observed_at=await database_now(self.session),
            registered_at=registry.registered_at,
            turn=schedule.turn,
            next_claim_at=schedule.next_claim_at,
            cooldown_until=schedule.cooldown_until,
            blocked_reason=schedule.blocked_reason,
            failed_source_id=delivery.source_id,
            attempt_no=attempt.attempt_no,
            lease_id=attempt.lease_id,
            started_at=attempt.started_at,
            ended_at=attempt.ended_at,
            delivery_updated_at=delivery.updated_at,
        )

    async def clear_block(self, expected: UmamiRecoveryState) -> bool:
        changed = await self.session.scalar(
            update(DeliveryScheduleRecord)
            .where(
                DeliveryScheduleRecord.sink == "umami",
                DeliveryScheduleRecord.blocked_reason == "destination_unavailable",
                DeliveryScheduleRecord.turn == expected.turn,
                DeliveryScheduleRecord.next_claim_at == expected.next_claim_at,
                DeliveryScheduleRecord.cooldown_until.is_not_distinct_from(expected.cooldown_until),
            )
            .values(blocked_reason=None)
            .returning(DeliveryScheduleRecord.sink)
        )
        return changed == "umami"
