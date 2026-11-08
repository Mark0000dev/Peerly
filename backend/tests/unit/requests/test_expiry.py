from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from studymate.application.requests.expiry import ExpireRequests
from studymate.application.requests.ports import RequestExpiryTransaction
from studymate.domain.requests.states import (
    REQUEST_LIFETIME,
    UNDO_WINDOW,
    ConnectionRequest,
    RequestState,
)
from tests.unit.identity_store import NOW
from tests.unit.requests.store import PEER
from tests.unit.requests.test_states import request

if TYPE_CHECKING:
    from uuid import UUID


class ExpiryStore:
    def __init__(self) -> None:
        first, second = request(), request().decline(PEER, NOW)
        self.requests = {first.id: first, second.id: second}
        self.clock = NOW + REQUEST_LIFETIME + timedelta(days=2)
        self.return_excess = False
        self.fail_after_first = False
        self.writes: list[UUID] = []

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[RequestExpiryTransaction]:
        before = self.requests.copy()
        try:
            yield self
        except BaseException:
            self.requests = before
            raise

    async def now(self) -> datetime:
        return self.clock

    async def due_requests(self, at: datetime, limit: int) -> tuple[ConnectionRequest, ...]:
        assert at == self.clock
        values = tuple(self.requests.values())
        return values if self.return_excess else values[:limit]

    async def save_request(self, value: ConnectionRequest) -> None:
        if self.writes and self.fail_after_first:
            raise RuntimeError("Synthetic second terminal write failure")
        self.requests[value.id] = value
        self.writes.append(value.id)


async def test_bounded_expiry_and_decline_settlement_use_effective_deadlines_once() -> None:
    store = ExpiryStore()
    result = await ExpireRequests(store)()
    assert {value.state for value in result} == {RequestState.EXPIRED, RequestState.DECLINED}
    by_state = {value.state: value for value in result}
    assert by_state[RequestState.EXPIRED].changed_at == NOW + REQUEST_LIFETIME
    assert by_state[RequestState.DECLINED].changed_at == NOW + UNDO_WINDOW
    assert await ExpireRequests(store)() == ()


@pytest.mark.parametrize("limit", [0, 101, True])
async def test_expiry_refuses_unbounded_or_invalid_batch(limit: int) -> None:
    with pytest.raises(ValueError, match="batch"):
        await ExpireRequests(ExpiryStore())(limit)


async def test_expiry_adapter_cannot_expand_requested_batch() -> None:
    store = ExpiryStore()
    store.return_excess = True
    with pytest.raises(RuntimeError, match="exceeded"):
        await ExpireRequests(store)(1)


async def test_expiry_rolls_back_partial_terminal_updates() -> None:
    store = ExpiryStore()
    before = store.requests.copy()
    store.fail_after_first = True
    with pytest.raises(RuntimeError, match="Synthetic second"):
        await ExpireRequests(store)()
    assert store.requests == before
