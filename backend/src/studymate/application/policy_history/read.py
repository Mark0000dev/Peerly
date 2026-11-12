from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from studymate.domain.registration import PolicyKind, PolicyReference
from studymate.domain.time import require_aware

MAX_POLICY_HISTORY_PAGE_SIZE = 50


@dataclass(frozen=True, slots=True)
class PolicyHistoryItem:
    reference: PolicyReference
    title: str


@dataclass(frozen=True, slots=True)
class PolicyHistoryPosition:
    published_at: datetime
    id: UUID
    as_of: datetime

    def __post_init__(self) -> None:
        require_aware(self.published_at)
        require_aware(self.as_of)
        if self.published_at > self.as_of:
            raise ValueError("Invalid policy history cursor")


@dataclass(frozen=True, slots=True)
class PolicyHistoryPage:
    items: tuple[PolicyHistoryItem, ...]
    next_position: PolicyHistoryPosition | None


class PolicyHistoryReader(Protocol):
    async def now(self) -> datetime: ...

    async def published_versions(
        self, kind: PolicyKind, before: PolicyHistoryPosition | None, limit: int, as_of: datetime
    ) -> tuple[PolicyHistoryItem, ...]:
        """Select only actually published metadata, newest first, with one lookahead."""
        ...


class PolicyHistoryUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[PolicyHistoryReader]: ...


@dataclass(frozen=True, slots=True)
class ReadPolicyHistory:
    unit_of_work: PolicyHistoryUnitOfWork

    async def __call__(
        self, kind: PolicyKind, before: PolicyHistoryPosition | None = None, limit: int = 20
    ) -> PolicyHistoryPage:
        if isinstance(limit, bool) or not 1 <= limit <= MAX_POLICY_HISTORY_PAGE_SIZE:
            raise ValueError("Policy history page size must be between 1 and 50")
        async with self.unit_of_work.transaction() as reader:
            now = await reader.now()
            if before is not None and before.as_of > now:
                raise ValueError("Invalid policy history cursor")
            as_of = before.as_of if before is not None else now
            rows = await reader.published_versions(kind, before, limit + 1, as_of)
        items = rows[:limit]
        position = None
        if len(rows) > limit:
            last = items[-1].reference
            position = PolicyHistoryPosition(last.published_at, last.id, as_of)
        return PolicyHistoryPage(items, position)
