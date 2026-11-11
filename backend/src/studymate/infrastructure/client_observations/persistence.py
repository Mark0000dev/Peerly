from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.client_observations.intake import (
    BATCHES_PER_MINUTE,
    ObservationAdmission,
    ObservationBatchIntent,
    ObservationBatchReceipt,
    ObservationRateLimitError,
    StoredObservation,
)
from studymate.application.idempotency import IntentKey
from studymate.domain.client_observations.events import (
    ActionObserved,
    ErrorObserved,
    HttpObserved,
    Observation,
    PerformanceObserved,
    QualityObserved,
)
from studymate.infrastructure.client_observations.models import (
    ClientObservationRecord,
    ObservationBatchRecord,
    ObservationFrameRecord,
)
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.transactions import open_transaction

RATE_WINDOW = timedelta(minutes=1)
RATE_RETRY_SECONDS = 60


def observation_record(
    event: Observation, owner: UUID, admission: ObservationAdmission, fingerprint: bytes
) -> ClientObservationRecord:
    record = ClientObservationRecord(
        id=uuid4(),
        account_id=owner,
        event_id=event.header.event_id,
        batch_key=admission.intent_key.value,
        fingerprint=fingerprint,
        schema_version=1,
        release_id=admission.release_id,
        observed_at=event.header.observed_at,
        received_at=admission.intent.receipt.received_at,
        kind=event.parts()[0],
        screen=event.header.screen.value,
    )
    if isinstance(event, ActionObserved):
        record.action, record.outcome, record.action_id = (
            event.action.value,
            event.outcome.value,
            event.action_id,
        )
    elif isinstance(event, PerformanceObserved):
        record.metric, record.value = event.metric.value, event.value
    elif isinstance(event, ErrorObserved):
        record.category = event.category.value
    elif isinstance(event, HttpObserved):
        record.method, record.route, record.status_class = (
            event.method.value,
            event.route.value,
            event.status_class.value,
        )
        record.duration_ms, record.request_id = event.duration_ms, event.request_id
        record.action_id, record.trace_id = event.action_id, event.trace_id
    elif isinstance(event, QualityObserved):
        record.quality_reason, record.quality_count = event.reason.value, event.count
    return record


@dataclass(frozen=True, slots=True)
class SqlObservationIntakeTransaction(SqlIdentityTransaction):
    async def prior_batch(self, actor_id: UUID, key: IntentKey) -> ObservationBatchIntent | None:
        record = await self.session.get(ObservationBatchRecord, (actor_id, key.value))
        if record is None:
            return None
        return ObservationBatchIntent(
            record.fingerprint,
            ObservationBatchReceipt(
                tuple(record.accepted_ids), tuple(record.duplicate_ids), record.received_at
            ),
        )

    async def observations(
        self, actor_id: UUID, event_ids: tuple[UUID, ...]
    ) -> tuple[StoredObservation, ...]:
        rows = (
            await self.session.execute(
                select(
                    ClientObservationRecord.account_id,
                    ClientObservationRecord.event_id,
                    ClientObservationRecord.fingerprint,
                ).where(
                    ClientObservationRecord.account_id == actor_id,
                    ClientObservationRecord.event_id.in_(event_ids),
                )
            )
        ).all()
        return tuple(StoredObservation(*row) for row in rows)

    async def admit_batch(self, actor_id: UUID, at: datetime) -> None:
        now = max(at, await self.now())
        count = await self.session.scalar(
            select(func.count())
            .select_from(ObservationBatchRecord)
            .where(
                ObservationBatchRecord.account_id == actor_id,
                ObservationBatchRecord.received_at > now - RATE_WINDOW,
            )
        )
        if count is None or count >= BATCHES_PER_MINUTE:
            raise ObservationRateLimitError(RATE_RETRY_SECONDS)

    async def save_batch(self, actor_id: UUID, admission: ObservationAdmission) -> None:
        receipt = admission.intent.receipt
        self.session.add(
            ObservationBatchRecord(
                account_id=actor_id,
                key=admission.intent_key.value,
                fingerprint=admission.intent.fingerprint,
                schema_version=1,
                release_id=admission.release_id,
                received_at=receipt.received_at,
                accepted_ids=list(receipt.accepted),
                duplicate_ids=list(receipt.duplicates),
            )
        )
        await self.session.flush()
        rows = tuple(
            observation_record(row.event, actor_id, admission, row.fingerprint)
            for row in admission.events
        )
        self.session.add_all(rows)
        await self.session.flush()
        for admitted, record in zip(admission.events, rows, strict=True):
            if isinstance(admitted.event, ErrorObserved) and admitted.event.frames:
                if admission.release_id is None:
                    raise RuntimeError("Accepted frame source lost its approved release identity")
                self.session.add_all(
                    ObservationFrameRecord(
                        observation_id=record.id,
                        frame_index=index,
                        kind="error.observed",
                        release_id=admission.release_id,
                        asset_id=frame.asset_id,
                        line=frame.line,
                        column_number=frame.column,
                    )
                    for index, frame in enumerate(admitted.event.frames)
                )
        await self.session.flush()


@dataclass(frozen=True, slots=True)
class SqlObservationIntakeUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlObservationIntakeTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlObservationIntakeTransaction(session)
