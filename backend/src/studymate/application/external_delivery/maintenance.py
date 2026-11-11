"""Explicit bounded maintenance; no startup historical Telegram replay."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

BACKFILL_BATCH = 100


class MaintenanceTransaction(Protocol):
    async def seed_umami(self, source_ids: tuple[UUID, ...]) -> int:
        """Insert ONLY actual canonical references in backfill_umami mode, conflict-safe."""
        ...


class MaintenanceUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[MaintenanceTransaction]: ...


@dataclass(frozen=True, slots=True)
class SeedUmamiBackfill:
    """Internal parent-operated use case, deliberately absent from public HTTP."""

    unit_of_work: MaintenanceUnitOfWork

    async def __call__(self, canonical_ids: tuple[UUID, ...]) -> int:
        if not 1 <= len(canonical_ids) <= BACKFILL_BATCH or len(set(canonical_ids)) != len(
            canonical_ids
        ):
            raise ValueError("Backfill needs1to100 distinct actual canonical event references")
        async with self.unit_of_work.transaction() as transaction:
            count = await transaction.seed_umami(canonical_ids)
            if not 0 <= count <= len(canonical_ids):
                raise RuntimeError("Backfill exceeded its explicit actual source selection")
            return count
