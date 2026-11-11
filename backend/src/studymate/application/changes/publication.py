"""Commit an ordered transport index only after its canonical sources are visible."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from studymate.domain.changes import ChangeHint, PublishedChange
from studymate.domain.time import require_aware

if TYPE_CHECKING:
    from uuid import UUID

PUBLICATION_BATCH_SIZE = 100


class ChangePublicationTransaction(Protocol):
    async def claim_changes(self, limit: int) -> tuple[ChangeHint, ...]:
        """Lock only queued committed canonical sources; skip other publishers' claims."""
        ...

    async def now(self) -> datetime: ...

    async def publish_changes(
        self, changes: tuple[ChangeHint, ...], at: datetime
    ) -> tuple[PublishedChange, ...]:
        """Lock recipient heads in UUID order, publish/mark claimed sources in this TX."""
        ...


class ChangePublicationUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[ChangePublicationTransaction]: ...


@dataclass(frozen=True, slots=True)
class PublishChanges:
    unit_of_work: ChangePublicationUnitOfWork

    async def __call__(self) -> int:
        async with self.unit_of_work.transaction() as transaction:
            changes = await transaction.claim_changes(PUBLICATION_BATCH_SIZE)
            keys = tuple((item.canonical_event_id, item.recipient_id) for item in changes)
            if len(changes) > PUBLICATION_BATCH_SIZE or len(keys) != len(set(keys)):
                raise RuntimeError("Publication source is duplicated or exceeds its bounded batch")
            if not changes:
                return 0
            at = await transaction.now()
            require_aware(at)
            published = await transaction.publish_changes(changes, at)
            if tuple(item.hint for item in published) != changes or any(
                item.published_at != at for item in published
            ):
                raise RuntimeError("Publication lost its actual claimed canonical sources")
            previous: dict[UUID, int] = {}
            for item in published:
                prior = previous.get(item.hint.recipient_id)
                if prior is not None and item.sequence != prior + 1:
                    raise RuntimeError(
                        "Publication skipped or reused a recipient delivery sequence"
                    )
                previous[item.hint.recipient_id] = item.sequence
            return len(published)
