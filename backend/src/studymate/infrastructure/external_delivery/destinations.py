"""Register immutable targets before worker leasing; credential rotation is separate."""

import hmac
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.domain.external_delivery.delivery import DestinationRef
from studymate.infrastructure.external_delivery.materialization import database_now
from studymate.infrastructure.external_delivery.models import DeliveryDestinationRecord
from studymate.infrastructure.persistence.transactions import open_transaction

FINGERPRINT_BYTES = 32


@dataclass(frozen=True, slots=True)
class DestinationRegistration:
    destination: DestinationRef
    fingerprint: bytes

    def __post_init__(self) -> None:
        if len(self.fingerprint) != FINGERPRINT_BYTES:
            raise ValueError("Destination registration requires its actual target fingerprint")


async def register_destinations(
    sessions: async_sessionmaker[AsyncSession], registrations: tuple[DestinationRegistration, ...]
) -> None:
    if len({item.destination.sink for item in registrations}) != len(registrations):
        raise ValueError("Only one current target per sink may be configured")
    async with open_transaction(sessions) as session:
        for item in sorted(registrations, key=lambda item: item.destination.sink):
            sink, revision = item.destination.sink.value, item.destination.revision
            await session.execute(
                insert(DeliveryDestinationRecord)
                .values(
                    sink=sink,
                    revision=revision,
                    fingerprint=item.fingerprint,
                    registered_at=await database_now(session),
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        DeliveryDestinationRecord.sink,
                        DeliveryDestinationRecord.revision,
                    ]
                )
            )
            existing = await session.scalar(
                select(DeliveryDestinationRecord).where(
                    DeliveryDestinationRecord.sink == sink,
                    DeliveryDestinationRecord.revision == revision,
                )
            )
            if existing is None or not hmac.compare_digest(existing.fingerprint, item.fingerprint):
                raise ValueError("Registered destination revision cannot change its actual target")
