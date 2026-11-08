from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest

from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.application.requests.queries import ListRequests, ReadRequest
from studymate.application.requests.query_ports import (
    RequestListQuery,
    RequestQueryTransaction,
    RequestReadRow,
)
from studymate.domain.requests.limits import SendQuota
from studymate.domain.requests.projections import RequestBox, RequestListView, RequestVisibility
from studymate.domain.requests.states import REQUEST_LIFETIME, RequestUnavailableError
from studymate.domain.requests.views import RequestDisclosure
from studymate.infrastructure.requests.cursors import FernetRequestCursorCodec
from tests.unit.identity_store import CREDENTIAL, NOW, IdentityStore
from tests.unit.requests.store import PEER
from tests.unit.requests.test_states import request
from tests.unit.requests.test_usecases import HASHER

PAGE_SIZE = 20


class QueryStore(IdentityStore):
    def __init__(self) -> None:
        super().__init__()
        self.actor = replace(self.actor, activation_complete=True)
        self.row = RequestReadRow(request(), RequestVisibility(False, True, True))
        self.rows: tuple[RequestReadRow, ...] = (self.row,)
        self.query: RequestListQuery | None = None
        self.disclosures: list[RequestDisclosure] = []
        self.unavailable = False
        self.expire_on_disclose = False

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[RequestQueryTransaction]:
        before = self.disclosures.copy()
        try:
            yield self
        except BaseException:
            self.disclosures = before
            raise

    async def list_requests(self, query: RequestListQuery) -> tuple[RequestReadRow, ...]:
        self.query = query
        return self.rows

    async def owned_request(self, actor_id: UUID, request_id: UUID) -> RequestReadRow | None:
        assert actor_id == self.actor.session.account_id
        assert request_id.int > 0
        return None if self.unavailable else self.row

    async def quota(self, actor_id: UUID, at: datetime) -> SendQuota:
        assert actor_id == self.actor.session.account_id
        assert at == self.clock
        return SendQuota(1, 3)

    async def unread_received(self, actor_id: UUID, at: datetime) -> int:
        assert actor_id == self.actor.session.account_id
        assert at == self.clock
        return 1

    async def disclose(self, source: RequestDisclosure) -> None:
        self.disclosures.append(source)
        if self.expire_on_disclose:
            self.clock = self.actor.session.expires_at


def listing(store: QueryStore) -> ListRequests:
    return ListRequests(store, HASHER, FernetRequestCursorCodec.from_key(b"x" * 32))


async def test_list_keyset_anchor_stays_fixed_without_ack_or_disclosure() -> None:
    store = QueryStore()
    store.rows = tuple(
        replace(store.row, request=replace(store.row.request, id=UUID(int=100 + index)))
        for index in range(PAGE_SIZE + 1)
    )
    page = await listing(store)(CREDENTIAL, RequestBox.SENT)
    assert len(page.requests) == PAGE_SIZE
    assert page.next_cursor is not None
    assert page.quota == SendQuota(1, 3)
    store.clock += timedelta(seconds=1)
    await listing(store)(CREDENTIAL, RequestBox.SENT, cursor=page.next_cursor)
    assert store.query is not None
    assert store.query.as_of == NOW
    assert store.query.cursor is not None
    assert store.query.cursor.request_id == store.rows[PAGE_SIZE - 1].request.id
    assert not store.disclosures


async def test_empty_list_has_no_cursor_and_recently_declined_is_received_only() -> None:
    store = QueryStore()
    store.rows = ()
    page = await listing(store)(CREDENTIAL, RequestBox.SENT)
    assert not page.requests
    assert page.next_cursor is None
    with pytest.raises(ValueError, match="received-only"):
        await listing(store)(CREDENTIAL, RequestBox.SENT, RequestListView.RECENTLY_DECLINED)


async def test_get_is_technical_disclosure_not_ack_even_at_effective_expiry() -> None:
    store = QueryStore()
    store.clock += REQUEST_LIFETIME
    store.actor = replace(
        store.actor,
        session=replace(store.actor.session, expires_at=store.clock + timedelta(hours=1)),
    )
    result = await ReadRequest(store, HASHER)(CREDENTIAL, store.row.request.id)
    assert result.disclosure.stored_version == store.row.request.version
    assert result.observation.version == store.row.request.version
    assert result.observation.state.value == "expired"
    assert store.disclosures == [result.disclosure]
    second = await ReadRequest(store, HASHER)(CREDENTIAL, store.row.request.id)
    assert second.disclosure.id != result.disclosure.id
    assert store.row.visibility.acknowledged is False


async def test_unknown_and_foreign_detail_are_unavailable() -> None:
    store = QueryStore()
    store.unavailable = True
    with pytest.raises(RequestUnavailableError):
        await ReadRequest(store, HASHER)(CREDENTIAL, uuid4())
    assert not store.disclosures
    store.unavailable = False
    with pytest.raises(RuntimeError, match="another request"):
        await ReadRequest(store, HASHER)(CREDENTIAL, uuid4())


async def test_read_checks_live_activation_and_rolls_back_on_session_expiry() -> None:
    store = QueryStore()
    store.actor = replace(store.actor, activation_complete=False)
    with pytest.raises(StudentActionDeniedError):
        await listing(store)(CREDENTIAL, RequestBox.SENT)
    store.actor = replace(store.actor, activation_complete=True)
    store.expire_on_disclose = True
    with pytest.raises(UnauthenticatedError):
        await ReadRequest(store, HASHER)(CREDENTIAL, store.row.request.id)
    assert not store.disclosures


async def test_list_rejects_wrong_direction_and_unbounded_adapter_result() -> None:
    store = QueryStore()
    with pytest.raises(RuntimeError, match="participant scope"):
        await listing(store)(CREDENTIAL, RequestBox.RECEIVED)
    store.rows = (store.row,) * (PAGE_SIZE + 2)
    with pytest.raises(RuntimeError, match="bounded projection"):
        await listing(store)(CREDENTIAL, RequestBox.SENT)
    store.actor = replace(store.actor, session=replace(store.actor.session, account_id=PEER))
    store.rows = (store.row,)
    result = await listing(store)(CREDENTIAL, RequestBox.RECEIVED)
    assert result.requests[0].unread
