"""Retained source references, not copies of business/private content."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.external_delivery.maintenance import (
    MaintenanceTransaction,
)
from studymate.infrastructure.external_delivery.models import (
    DeliverySourceRecord,
)
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.transactions import open_transaction


@dataclass(frozen=True, slots=True)
class SqlMaintenanceTransaction:
    session: AsyncSession

    async def seed_umami(self, source_ids: tuple[UUID, ...]) -> int:
        actual = tuple(
            (
                await self.session.scalars(
                    select(ProductEventRecord.id).where(ProductEventRecord.id.in_(source_ids))
                )
            ).all()
        )
        if set(actual) != set(source_ids):
            raise ValueError("Backfill requires actual retained canonical source rows")
        inserted = (
            await self.session.scalars(
                insert(DeliverySourceRecord)
                .values(
                    [
                        {
                            "canonical_event_id": identifier,
                            "source_kind": "canonical",
                            "mode": "backfill_umami",
                        }
                        for identifier in source_ids
                    ]
                )
                .on_conflict_do_nothing(index_elements=[DeliverySourceRecord.canonical_event_id])
                .returning(DeliverySourceRecord.id)
            )
        ).all()
        return len(inserted)


@dataclass(frozen=True, slots=True)
class SqlMaintenanceUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[MaintenanceTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlMaintenanceTransaction(session)
