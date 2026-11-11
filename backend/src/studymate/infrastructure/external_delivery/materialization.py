from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, cast, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.external_delivery.routing import MATERIALIZATION_BATCH, RoutePlan
from studymate.domain.external_delivery.sources import CapturedSource
from studymate.infrastructure.external_delivery.models import (
    DeliverySourceRecord,
    ExternalDeliveryRecord,
)
from studymate.infrastructure.external_delivery.source_reads import SelectedSourceLoader
from studymate.infrastructure.persistence.transactions import open_transaction


async def database_now(session: AsyncSession) -> datetime:
    return (
        await session.scalars(select(cast(func.clock_timestamp(), DateTime(timezone=True))))
    ).one()


@dataclass(frozen=True, slots=True)
class SqlMaterializationTransaction:
    session: AsyncSession
    claimed: dict[UUID, CapturedSource] = field(default_factory=dict, repr=False)

    async def sources(self, limit: int) -> tuple[CapturedSource, ...]:
        if isinstance(limit, bool) or not 1 <= limit <= MATERIALIZATION_BATCH:
            raise ValueError("Source materialization requires its bounded claim size")
        rows = tuple(
            await self.session.scalars(
                select(DeliverySourceRecord)
                .where(DeliverySourceRecord.materialized_at.is_(None))
                .order_by(DeliverySourceRecord.captured_at, DeliverySourceRecord.id)
                .with_for_update(skip_locked=True)
                .limit(limit)
            )
        )
        sources = await SelectedSourceLoader(self.session).load(rows)
        self.claimed.update((source.id, source) for source in sources)
        return sources

    async def materialize(self, plan: RoutePlan) -> None:
        source = self.claimed.get(plan.source_id)
        if source is None or plan.routing_version != source.routing_version:
            raise RuntimeError("External routing lost its actual locked source/version")
        now = await database_now(self.session)
        for target in plan.targets:
            await self.session.execute(
                insert(ExternalDeliveryRecord)
                .values(
                    id=uuid4(),
                    source_id=source.id,
                    sink=target.sink.value,
                    destination_revision=None,
                    projection_version=1,
                    state="pending",
                    attempt_count=0,
                    next_attempt_at=now,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_nothing(
                    index_elements=[ExternalDeliveryRecord.source_id, ExternalDeliveryRecord.sink]
                )
            )
        record = await self.session.get(DeliverySourceRecord, source.id)
        if record is None or record.materialized_at is not None:
            raise RuntimeError("External materialization lost its actual pending capture")
        record.materialized_at = now
        record.exclusion_reason = plan.exclusion_reason.value
        await self.session.flush()
        del self.claimed[source.id]


@dataclass(frozen=True, slots=True)
class SqlMaterializationUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlMaterializationTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlMaterializationTransaction(session)
