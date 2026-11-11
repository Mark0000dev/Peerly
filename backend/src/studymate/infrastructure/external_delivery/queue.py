"""Short SQL lease transactions; provider HTTP always runs after return/commit."""

from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.external_delivery.routing import route_source
from studymate.application.external_delivery.worker import plan_completion
from studymate.domain.external_delivery.delivery import (
    DeliveryLease,
    DeliveryResult,
    DeliveryState,
    DestinationRef,
    FailureCode,
    ResultKind,
)
from studymate.domain.external_delivery.sources import Sink
from studymate.infrastructure.external_delivery.materialization import database_now
from studymate.infrastructure.external_delivery.models import (
    DeliveryAttemptRecord,
    DeliveryDestinationRecord,
    DeliveryScheduleRecord,
    DeliverySourceRecord,
    ExternalDeliveryRecord,
)
from studymate.infrastructure.external_delivery.source_reads import SelectedSourceLoader
from studymate.infrastructure.persistence.transactions import open_transaction

MAX_LEASE_SECONDS = 60


async def schedule_row(session: AsyncSession, sink: Sink) -> DeliveryScheduleRecord:
    row = await session.scalar(
        select(DeliveryScheduleRecord)
        .where(DeliveryScheduleRecord.sink == sink.value)
        .with_for_update()
    )
    if row is None:
        raise RuntimeError("External delivery schedule requires its actual seeded sink")
    return row


async def expire_one(session: AsyncSession, sink: Sink) -> None:
    now = await database_now(session)
    delivery = await session.scalar(
        select(ExternalDeliveryRecord)
        .where(
            ExternalDeliveryRecord.sink == sink.value,
            ExternalDeliveryRecord.state == "leased",
            ExternalDeliveryRecord.lease_until <= now,
        )
        .order_by(ExternalDeliveryRecord.lease_until, ExternalDeliveryRecord.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if delivery is None:
        return
    attempt = await session.get(DeliveryAttemptRecord, (delivery.id, delivery.attempt_count))
    if attempt is None or attempt.lease_id != delivery.lease_id or attempt.ended_at is not None:
        raise RuntimeError("Expired delivery lost its actual open source attempt")
    plan = plan_completion(
        delivery.attempt_count, DeliveryResult(ResultKind.AMBIGUOUS, FailureCode.LEASE_EXPIRED), now
    )
    attempt.ended_at, attempt.outcome, attempt.failure = (
        now,
        "lease_expired",
        FailureCode.LEASE_EXPIRED.value,
    )
    delivery.state, delivery.next_attempt_at = plan.state.value, plan.next_attempt_at
    delivery.lease_id, delivery.lease_until = None, None
    delivery.updated_at, delivery.last_failure = now, FailureCode.LEASE_EXPIRED.value
    await session.flush()


@dataclass(frozen=True, slots=True)
class SqlExternalDeliveryQueue:
    sessions: async_sessionmaker[AsyncSession]

    async def next_sink(self, excluded: frozenset[Sink]) -> Sink | None:
        async with open_transaction(self.sessions) as session:
            row = await session.scalar(
                select(DeliveryScheduleRecord)
                .where(DeliveryScheduleRecord.sink.not_in(tuple(sink.value for sink in excluded)))
                .order_by(DeliveryScheduleRecord.next_claim_at, DeliveryScheduleRecord.turn)
                .limit(1)
            )
            return Sink(row.sink) if row is not None else None

    async def claim(self, destination: DestinationRef, lease_seconds: int) -> DeliveryLease | None:
        if isinstance(lease_seconds, bool) or not 1 <= lease_seconds <= MAX_LEASE_SECONDS:
            raise ValueError("External delivery lease lifetime is outside its worker bound")
        async with open_transaction(self.sessions) as session:
            schedule = await schedule_row(session, destination.sink)
            now = await database_now(session)
            if schedule.blocked_reason is not None or (
                schedule.cooldown_until is not None and schedule.cooldown_until > now
            ):
                return None
            registered = await session.get(
                DeliveryDestinationRecord, (destination.sink.value, destination.revision)
            )
            if registered is None:
                return None
            await expire_one(session, destination.sink)
            row = await session.scalar(
                select(ExternalDeliveryRecord)
                .where(
                    ExternalDeliveryRecord.sink == destination.sink.value,
                    ExternalDeliveryRecord.state.in_(("pending", "retry")),
                    ExternalDeliveryRecord.next_attempt_at <= now,
                    or_(
                        ExternalDeliveryRecord.destination_revision.is_(None),
                        ExternalDeliveryRecord.destination_revision == destination.revision,
                    ),
                )
                .order_by(ExternalDeliveryRecord.next_attempt_at, ExternalDeliveryRecord.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if row is None:
                return None
            source = await session.get(DeliverySourceRecord, row.source_id)
            if source is None:
                raise RuntimeError("External delivery lost its immutable captured source")
            fact = (await SelectedSourceLoader(session).load((source,)))[0]
            plan = route_source(fact)
            target = next(
                (target for target in plan.targets if target.sink == destination.sink), None
            )
            if target is None or row.projection_version != 1:
                raise RuntimeError(
                    "External delivery has no matching versioned actual source route"
                )
            now = await database_now(session)
            row.destination_revision = destination.revision
            row.attempt_count += 1
            row.state, row.lease_id, row.lease_until = (
                "leased",
                uuid4(),
                now + timedelta(seconds=lease_seconds),
            )
            row.updated_at = now
            schedule.next_claim_at = now
            session.add(
                DeliveryAttemptRecord(
                    delivery_id=row.id,
                    attempt_no=row.attempt_count,
                    lease_id=row.lease_id,
                    started_at=now,
                )
            )
            await session.flush()
            return DeliveryLease(
                row.id,
                row.source_id,
                destination,
                row.lease_id,
                row.attempt_count,
                now,
                row.lease_until,
                target.payload,
                row.projection_version,
            )

    async def finish(self, lease: DeliveryLease, result: DeliveryResult) -> None:
        async with open_transaction(self.sessions) as session:
            schedule = await schedule_row(session, lease.destination.sink)
            row = await session.scalar(
                select(ExternalDeliveryRecord)
                .where(ExternalDeliveryRecord.id == lease.delivery_id)
                .with_for_update()
            )
            attempt = await session.get(
                DeliveryAttemptRecord, (lease.delivery_id, lease.attempt_no), with_for_update=True
            )
            if row is None or attempt is None or attempt.lease_id != lease.lease_id:
                raise RuntimeError("External completion lost its actual source attempt")
            if row.source_id != lease.source_id or row.sink != lease.destination.sink.value:
                raise RuntimeError("External completion differs from its original source/sink")
            if result.provider_message_id is not None and lease.destination.sink == Sink.UMAMI:
                raise RuntimeError("Umami cannot claim a Telegram message receipt")
            now = await database_now(session)
            if row.lease_id != lease.lease_id or row.state != "leased":
                if (
                    result.kind == ResultKind.ACCEPTED
                    and attempt.outcome != "accepted"
                    and attempt.late_ack_at is None
                ):
                    attempt.late_ack_at, attempt.late_message_id = now, result.provider_message_id
                    await session.flush()
                return
            if (
                row.destination_revision != lease.destination.revision
                or attempt.ended_at is not None
            ):
                raise RuntimeError(
                    "External completion changed its leased destination or closed attempt"
                )
            plan = plan_completion(lease.attempt_no, result, now)
            attempt.ended_at, attempt.outcome = now, result.kind.value
            attempt.failure = result.failure.value if result.failure is not None else None
            attempt.http_status, attempt.retry_after_seconds = (
                result.http_status,
                result.retry_after_seconds,
            )
            attempt.provider_message_id = result.provider_message_id
            row.state, row.next_attempt_at = plan.state.value, plan.next_attempt_at
            row.lease_id, row.lease_until = None, None
            row.updated_at = now
            row.last_failure = result.failure.value if result.failure is not None else None
            if plan.state == DeliveryState.SUCCEEDED:
                row.delivered_at, row.provider_message_id = now, result.provider_message_id
            if plan.cooldown_until is not None:
                schedule.cooldown_until = (
                    max(schedule.cooldown_until, plan.cooldown_until)
                    if schedule.cooldown_until is not None
                    else plan.cooldown_until
                )
            if plan.block_sink:
                schedule.blocked_reason = (
                    result.failure.value
                    if result.failure is not None
                    else FailureCode.PERMANENT.value
                )
            await session.flush()
