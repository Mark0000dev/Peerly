from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest

from studymate.application.changes.retention import (
    CHANGE_RETENTION,
    RETENTION_PREFIX_LIMIT,
    RETENTION_RECIPIENT_BATCH,
    ChangeRetentionTransaction,
    PruneChanges,
)
from tests.unit.identity_store import NOW


@dataclass(slots=True)
class Store:
    result: int = 0
    calls: tuple[tuple[datetime, int, int], ...] = ()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[ChangeRetentionTransaction]:
        yield self

    async def now(self) -> datetime:
        return NOW

    async def prune_changes(self, before: datetime, recipients: int, per_recipient: int) -> int:
        self.calls += ((before, recipients, per_recipient),)
        return self.result


async def test_transport_retention_uses_actual_clock_and_fixed_bounded_prefixes() -> None:
    store = Store(result=1)
    assert await PruneChanges(store)() == store.result
    assert store.calls == (
        (NOW - CHANGE_RETENTION, RETENTION_RECIPIENT_BATCH, RETENTION_PREFIX_LIMIT),
    )


@pytest.mark.parametrize("duration", [timedelta(), timedelta(seconds=-1)])
def test_nonpositive_retention_cannot_silently_erase_current_transport(duration: timedelta) -> None:
    with pytest.raises(ValueError, match="positive"):
        PruneChanges(Store(), duration)


@pytest.mark.parametrize(
    "count", [True, -1, RETENTION_PREFIX_LIMIT * RETENTION_RECIPIENT_BATCH + 1]
)
async def test_worker_rejects_fabricated_or_unbounded_removed_counts(count: int) -> None:
    with pytest.raises(RuntimeError, match="bounded source range"):
        await PruneChanges(Store(result=count))()
