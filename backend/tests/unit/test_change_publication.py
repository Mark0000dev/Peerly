from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest

from studymate.application.changes.publication import (
    PUBLICATION_BATCH_SIZE,
    ChangePublicationTransaction,
    PublishChanges,
)
from studymate.domain.changes import ChangeHint, ChangeResource, PublishedChange
from tests.unit.identity_store import NOW


def hint(recipient: int = 2) -> ChangeHint:
    return ChangeHint(uuid4(), UUID(int=recipient), ChangeResource.CONVERSATION, uuid4(), None)


class Store:
    def __init__(self) -> None:
        self.pending: tuple[ChangeHint, ...] = ()
        self.heads: dict[UUID, int] = {}
        self.published: tuple[PublishedChange, ...] = ()
        self.malformation: str | None = None
        self.writes = 0

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[ChangePublicationTransaction]:
        original = self.pending, self.heads.copy(), self.published
        try:
            yield self
        except BaseException:
            self.pending, self.heads, self.published = original
            raise

    async def claim_changes(self, limit: int) -> tuple[ChangeHint, ...]:
        assert limit == PUBLICATION_BATCH_SIZE
        return self.pending

    async def now(self) -> datetime:
        return NOW

    async def publish_changes(
        self, changes: tuple[ChangeHint, ...], at: datetime
    ) -> tuple[PublishedChange, ...]:
        self.writes += 1
        result: list[PublishedChange] = []
        for item in changes:
            sequence = self.heads.get(item.recipient_id, 0) + 1
            self.heads[item.recipient_id] = sequence
            result.append(PublishedChange(item, sequence, at))
        self.pending = ()
        self.published += tuple(result)
        if self.malformation == "source":
            result[0] = replace(result[0], hint=hint())
        elif self.malformation == "time":
            result[0] = replace(result[0], published_at=at + timedelta(seconds=1))
        elif self.malformation == "gap":
            result[-1] = replace(result[-1], sequence=result[-1].sequence + 1)
        elif self.malformation == "reused":
            result[-1] = replace(result[-1], sequence=result[0].sequence)
        elif self.malformation == "omitted":
            result.pop()
        return tuple(result)


async def test_idle_publication_neither_spends_sequences_nor_creates_a_fake_event() -> None:
    store = Store()
    assert await PublishChanges(store)() == 0
    assert store.writes == 0
    assert not store.heads
    assert not store.published


async def test_recipients_get_independent_contiguous_sequences_only_for_committed_sources() -> None:
    store = Store()
    sources = (hint(2), hint(3), hint(2))
    store.pending = sources
    assert await PublishChanges(store)() == len(sources)
    assert tuple(item.hint for item in store.published) == sources
    assert tuple(item.sequence for item in store.published) == (1, 1, 2)
    assert await PublishChanges(store)() == 0
    previous = store.heads[UUID(int=2)]
    store.pending = (hint(2),)
    assert await PublishChanges(store)() == 1
    assert store.published[-1].sequence == previous + 1


@pytest.mark.parametrize("malformation", ["source", "time", "gap", "reused", "omitted"])
async def test_mismatched_publication_rolls_back_claims_and_does_not_spend_a_sequence(
    malformation: str,
) -> None:
    store = Store()
    sources = (hint(), hint())
    store.pending = sources
    store.malformation = malformation
    with pytest.raises(RuntimeError):
        await PublishChanges(store)()
    assert store.pending == sources
    assert not store.heads
    assert not store.published
    store.malformation = None
    assert await PublishChanges(store)() == len(sources)
    assert tuple(item.sequence for item in store.published) == (1, 2)


@pytest.mark.parametrize("malformation", ["duplicate", "unbounded"])
async def test_unbounded_or_duplicate_claims_fail_before_publication(malformation: str) -> None:
    store = Store()
    source = hint()
    store.pending = (
        (source, source)
        if malformation == "duplicate"
        else tuple(hint() for _ in range(PUBLICATION_BATCH_SIZE + 1))
    )
    with pytest.raises(RuntimeError):
        await PublishChanges(store)()
    assert store.writes == 0
    assert not store.published
