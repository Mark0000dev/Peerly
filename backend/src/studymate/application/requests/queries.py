from dataclasses import dataclass
from uuid import UUID, uuid4

from studymate.application.identity.sessions import (
    IdentitySnapshot,
    SessionCredential,
    SessionHasher,
    StudentActionDeniedError,
    UnauthenticatedError,
    require_verified_student,
)
from studymate.application.requests.cursors import RequestCursor, RequestCursorCodec
from studymate.application.requests.query_ports import (
    REQUEST_PAGE_SIZE,
    RequestDetail,
    RequestListQuery,
    RequestPage,
    RequestQueryTransaction,
    RequestQueryUnitOfWork,
)
from studymate.domain.requests.projections import (
    RequestBox,
    RequestListView,
    observe_request,
    request_box,
)
from studymate.domain.requests.states import RequestUnavailableError
from studymate.domain.requests.views import RequestDisclosure


async def query_actor(
    transaction: RequestQueryTransaction, credential: SessionCredential, hasher: SessionHasher
) -> IdentitySnapshot:
    actor, _ = await require_verified_student(transaction, await hasher.digest(credential))
    if not actor.activation_complete:
        raise StudentActionDeniedError
    return actor


async def query_finish(transaction: RequestQueryTransaction, actor: IdentitySnapshot) -> None:
    if not actor.session.is_active(await transaction.now()):
        raise UnauthenticatedError


@dataclass(frozen=True, slots=True)
class ListRequests:
    unit_of_work: RequestQueryUnitOfWork
    hasher: SessionHasher
    cursor_codec: RequestCursorCodec

    async def __call__(
        self,
        credential: SessionCredential,
        box: RequestBox,
        view: RequestListView = RequestListView.ACTIVE,
        cursor: str | None = None,
    ) -> RequestPage:
        async with self.unit_of_work.transaction() as transaction:
            actor = await query_actor(transaction, credential, self.hasher)
            actor_id = actor.session.account_id
            now = await transaction.now()
            position = (
                self.cursor_codec.decode(actor_id, box, view, cursor, now)
                if cursor is not None
                else None
            )
            query = RequestListQuery(
                actor_id, box, view, now if position is None else position.as_of, position
            )
            rows = await transaction.list_requests(query)
            if len(rows) > REQUEST_PAGE_SIZE + 1:
                raise RuntimeError("Request list exceeded its bounded projection")
            for row in rows:
                if request_box(row.request, actor_id) != box:
                    raise RuntimeError("Request list returned another participant scope")
            visible = rows[:REQUEST_PAGE_SIZE]
            next_cursor = None
            if len(rows) > REQUEST_PAGE_SIZE:
                last = visible[-1].request
                next_cursor = self.cursor_codec.encode(
                    actor_id, box, view, RequestCursor(query.as_of, last.sent_at, last.id)
                )
            result = RequestPage(
                tuple(
                    observe_request(row.request, actor_id, now, row.visibility, row.peer)
                    for row in visible
                ),
                next_cursor,
                now,
                await transaction.quota(actor_id, now),
                await transaction.unread_received(actor_id, now),
            )
            await query_finish(transaction, actor)
            return result


@dataclass(frozen=True, slots=True)
class ReadRequest:
    unit_of_work: RequestQueryUnitOfWork
    hasher: SessionHasher

    async def __call__(self, credential: SessionCredential, request_id: UUID) -> RequestDetail:
        async with self.unit_of_work.transaction() as transaction:
            actor = await query_actor(transaction, credential, self.hasher)
            actor_id = actor.session.account_id
            row = await transaction.owned_request(actor_id, request_id)
            if row is None:
                raise RequestUnavailableError
            if row.request.id != request_id:
                raise RuntimeError("Request detail returned another request")
            request_box(row.request, actor_id)
            now = await transaction.now()
            disclosure = RequestDisclosure(uuid4(), actor_id, request_id, row.request.version, now)
            await transaction.disclose(disclosure)
            result = RequestDetail(
                observe_request(row.request, actor_id, now, row.visibility, row.peer), disclosure
            )
            await query_finish(transaction, actor)
            return result
