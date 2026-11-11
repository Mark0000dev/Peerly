"""Audited retained metadata: bounded bulk queries, no provider content or secrets."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.external_delivery.inspection import SourceFilters
from studymate.domain.external_delivery.delivery import (
    MAX_ATTEMPTS,
    DeliveryState,
    FailureCode,
    ResultKind,
)
from studymate.domain.external_delivery.inspection import (
    PAGE_SIZE,
    AttemptSummary,
    DeliverySummary,
    SourceDetail,
    SourceSummary,
)
from studymate.domain.external_delivery.sources import (
    CapturedSource,
    CaptureMode,
    Sink,
    SourceKind,
)
from studymate.infrastructure.client_observations.models import ClientObservationRecord
from studymate.infrastructure.external_delivery.models import (
    DeliveryAttemptRecord,
    DeliverySourceRecord,
    ExternalDeliveryRecord,
)
from studymate.infrastructure.external_delivery.source_reads import SelectedSourceLoader
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.transactions import open_transaction
from studymate.infrastructure.support.models import SupportCaseRecord

MAX_SOURCE_ATTEMPTS = len(Sink) * MAX_ATTEMPTS


def summary(row: DeliverySourceRecord, source: CapturedSource) -> SourceSummary:
    fact = source.source
    actor = fact.actor_id
    return SourceSummary(
        row.id,
        SourceKind(row.source_kind),
        fact.id,
        actor,
        row.captured_at,
        CaptureMode(row.mode),
        row.routing_version,
        row.materialized_at,
        row.exclusion_reason,
    )


def attempt_summary(row: DeliveryAttemptRecord) -> AttemptSummary:
    return AttemptSummary(
        row.attempt_no,
        row.lease_id,
        row.started_at,
        row.ended_at,
        ResultKind(row.outcome)
        if row.outcome is not None and row.outcome != "lease_expired"
        else None,
        row.outcome == "lease_expired",
        FailureCode(row.failure) if row.failure is not None else None,
        row.http_status,
        row.retry_after_seconds,
        row.provider_message_id,
        row.late_ack_at,
        row.late_message_id,
    )


@dataclass(frozen=True, slots=True)
class SqlSourceInspectionTransaction(SqlOperatorTransaction):
    async def sources(
        self, filters: SourceFilters, before_id: UUID | None
    ) -> tuple[SourceSummary, ...]:
        self.checked_access()
        statement = select(DeliverySourceRecord)
        if filters.kind is not None:
            statement = statement.where(DeliverySourceRecord.source_kind == filters.kind.value)
        if filters.actor_id is not None:
            statement = statement.where(
                or_(
                    DeliverySourceRecord.canonical_event_id.in_(
                        select(ProductEventRecord.id).where(
                            ProductEventRecord.account_id == filters.actor_id
                        )
                    ),
                    DeliverySourceRecord.observation_id.in_(
                        select(ClientObservationRecord.id).where(
                            ClientObservationRecord.account_id == filters.actor_id
                        )
                    ),
                    DeliverySourceRecord.support_case_id.in_(
                        select(SupportCaseRecord.id).where(
                            SupportCaseRecord.actor_id == filters.actor_id
                        )
                    ),
                )
            )
        if before_id is not None:
            statement = statement.where(DeliverySourceRecord.id < before_id)
        rows = tuple(
            await self.session.scalars(
                statement.order_by(DeliverySourceRecord.id.desc()).limit(PAGE_SIZE + 1)
            )
        )
        sources = await SelectedSourceLoader(self.session).load(rows)
        return tuple(summary(row, source) for row, source in zip(rows, sources, strict=True))

    async def source(self, source_id: UUID) -> SourceDetail | None:
        self.checked_access()
        row = await self.session.get(DeliverySourceRecord, source_id)
        if row is None:
            return None
        source = (await SelectedSourceLoader(self.session).load((row,)))[0]
        deliveries = tuple(
            await self.session.scalars(
                select(ExternalDeliveryRecord)
                .where(ExternalDeliveryRecord.source_id == source_id)
                .order_by(ExternalDeliveryRecord.sink)
                .limit(len(Sink) + 1)
            )
        )
        if len(deliveries) > len(Sink):
            raise RuntimeError("Source inspection exceeded its actual finite destination set")
        attempts = tuple(
            await self.session.scalars(
                select(DeliveryAttemptRecord)
                .where(
                    DeliveryAttemptRecord.delivery_id.in_(
                        tuple(delivery.id for delivery in deliveries)
                    )
                )
                .order_by(DeliveryAttemptRecord.delivery_id, DeliveryAttemptRecord.attempt_no)
                .limit(MAX_SOURCE_ATTEMPTS + 1)
            )
        )
        if len(attempts) > MAX_SOURCE_ATTEMPTS:
            raise RuntimeError("Source inspection exceeded its bounded retained attempts")
        selected = tuple(
            DeliverySummary(
                delivery.id,
                Sink(delivery.sink),
                delivery.destination_revision,
                delivery.projection_version,
                DeliveryState(delivery.state),
                delivery.next_attempt_at,
                delivery.lease_until,
                delivery.created_at,
                delivery.updated_at,
                delivery.delivered_at,
                delivery.provider_message_id,
                FailureCode(delivery.last_failure) if delivery.last_failure else None,
                tuple(
                    attempt_summary(attempt)
                    for attempt in attempts
                    if attempt.delivery_id == delivery.id
                ),
            )
            for delivery in deliveries
        )
        return SourceDetail(summary(row, source), source, selected)


@dataclass(frozen=True, slots=True)
class SqlSourceInspectionUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: OperatorAuditRecorder

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlSourceInspectionTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlSourceInspectionTransaction(session, self.recorder)
