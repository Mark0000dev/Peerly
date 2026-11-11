"""Expire only transport hints; canonical outcomes and business history remain retained."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from studymate.domain.time import require_aware

CHANGE_RETENTION = timedelta(hours=24)
RETENTION_RECIPIENT_BATCH = 20
RETENTION_PREFIX_LIMIT = 1000


class ChangeRetentionTransaction(Protocol):
    async def now(self) -> datetime: ...

    async def prune_changes(self, before: datetime, recipients: int, per_recipient: int) -> int:
        """Lock recipient heads; remove only old contiguous prefixes and advance reset floors."""
        ...


class ChangeRetentionUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[ChangeRetentionTransaction]: ...


@dataclass(frozen=True, slots=True)
class PruneChanges:
    unit_of_work: ChangeRetentionUnitOfWork
    retention: timedelta = CHANGE_RETENTION

    def __post_init__(self) -> None:
        if self.retention <= timedelta():
            raise ValueError("Transport retention must be positive")

    async def __call__(self) -> int:
        async with self.unit_of_work.transaction() as transaction:
            now = await transaction.now()
            require_aware(now)
            removed = await transaction.prune_changes(
                now - self.retention, RETENTION_RECIPIENT_BATCH, RETENTION_PREFIX_LIMIT
            )
            if (
                isinstance(removed, bool)
                or not 0 <= removed <= RETENTION_RECIPIENT_BATCH * RETENTION_PREFIX_LIMIT
            ):
                raise RuntimeError("Transport retention exceeded its bounded source range")
            return removed
