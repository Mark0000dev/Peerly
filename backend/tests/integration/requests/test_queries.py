import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.requests.queries import ListRequests, ReadRequest
from studymate.application.requests.viewing import AcknowledgeRequestViewed, ViewRequestCommand
from studymate.domain.requests.projections import (
    RequestBox,
    RequestListView,
    RequestPeerState,
    RequestPublicState,
)
from studymate.domain.requests.states import RequestUnavailableError
from studymate.domain.requests.views import RequestViewReceipt
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_request_viewed
from studymate.infrastructure.requests.cursors import FernetRequestCursorCodec
from studymate.infrastructure.requests.queries import SqlRequestQueryUnitOfWork
from studymate.infrastructure.requests.view_models import (
    RequestDisclosureRecord,
    RequestViewAcknowledgementRecord,
)
from studymate.infrastructure.requests.viewing import SqlRequestViewUnitOfWork
from tests.integration.profile_lifecycle_fixture import command as visibility_command
from tests.integration.profile_lifecycle_fixture import services as visibility_services
from tests.integration.requests.fixture import (
    FINGERPRINTER,
    HASHER,
    action,
    additional_peer,
    prepared,
    sent,
)

pytestmark = pytest.mark.integration
EXPECTED_DETAIL_SOURCES = 2


async def test_detail_is_not_viewed_and_ack_commits_once_for_original_owned_source(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    value = await sent(api, sender, recipient)
    query = SqlRequestQueryUnitOfWork(api.sessions)
    listing = ListRequests(query, HASHER, codec())
    read = ReadRequest(query, HASHER)
    detail = await read(recipient.credential, value.id)
    repeated = await read(recipient.credential, value.id)
    assert repeated.disclosure.id != detail.disclosure.id
    assert detail.observation.unread
    assert detail.observation.version == value.version
    ack = AcknowledgeRequestViewed(
        SqlRequestViewUnitOfWork(api.sessions, record_request_viewed), HASHER, FINGERPRINTER
    )
    command = ViewRequestCommand(
        recipient.credential, value.id, detail.disclosure.id, IntentKey(str(uuid4()))
    )
    first = await ack(command)
    assert await ack(command) == first
    second = await ack(
        ViewRequestCommand(
            recipient.credential, value.id, repeated.disclosure.id, IntentKey(str(uuid4()))
        )
    )
    assert second == first
    with pytest.raises(IdempotencyConflictError):
        await ack(
            ViewRequestCommand(recipient.credential, value.id, repeated.disclosure.id, command.key)
        )
    page = await listing(recipient.credential, RequestBox.RECEIVED)
    assert page.requests[0].unread is False
    assert page.unread_received == 0
    assert page.requests[0].peer.display_name is not None
    async with api.sessions() as session:
        assert (
            await session.scalar(select(func.count()).select_from(RequestDisclosureRecord))
            == EXPECTED_DETAIL_SOURCES
        )
        assert (
            await session.scalar(select(func.count()).select_from(RequestViewAcknowledgementRecord))
            == 1
        )
        event = (
            await session.scalars(
                select(ProductEventRecord).where(
                    ProductEventRecord.kind == "request.view_acknowledged"
                )
            )
        ).one()
        assert event.account_id == recipient.id
        assert event.request_view_ack_id == first.id


def codec() -> FernetRequestCursorCodec:
    return FernetRequestCursorCodec.from_key(b"x" * 32)


async def test_disclosure_is_bound_to_live_actor_request_and_source(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    value = await sent(api, sender, recipient)
    query = SqlRequestQueryUnitOfWork(api.sessions)
    read = ReadRequest(query, HASHER)
    detail = await read(recipient.credential, value.id)
    other = await additional_peer(identity_engine, value.context.subject_id)
    with pytest.raises(RequestUnavailableError):
        await read(other.credential, value.id)
    with pytest.raises(RequestUnavailableError):
        await read(other.credential, uuid4())
    ack = AcknowledgeRequestViewed(
        SqlRequestViewUnitOfWork(api.sessions, record_request_viewed), HASHER, FINGERPRINTER
    )
    with pytest.raises(RequestUnavailableError):
        await ack(
            ViewRequestCommand(
                sender.credential, value.id, detail.disclosure.id, IntentKey(str(uuid4()))
            )
        )
    with pytest.raises(RequestUnavailableError):
        await ack(
            ViewRequestCommand(
                recipient.credential, uuid4(), detail.disclosure.id, IntentKey(str(uuid4()))
            )
        )
    async with api.sessions() as session:
        assert (
            await session.scalar(select(func.count()).select_from(RequestViewAcknowledgementRecord))
            == 0
        )


async def test_ack_race_and_canonical_failure_rollback_receipt_and_intent(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    value = await sent(api, sender, recipient)
    query = SqlRequestQueryUnitOfWork(api.sessions)
    detail = await ReadRequest(query, HASHER)(recipient.credential, value.id)

    async def failing(session: AsyncSession, receipt: RequestViewReceipt) -> None:
        await record_request_viewed(session, receipt)
        raise RuntimeError("Synthetic after canonical ACK")

    broken = AcknowledgeRequestViewed(
        SqlRequestViewUnitOfWork(api.sessions, failing), HASHER, FINGERPRINTER
    )
    command = ViewRequestCommand(
        recipient.credential, value.id, detail.disclosure.id, IntentKey(str(uuid4()))
    )
    with pytest.raises(RuntimeError, match="after canonical"):
        await broken(command)
    ack = AcknowledgeRequestViewed(
        SqlRequestViewUnitOfWork(api.sessions, record_request_viewed), HASHER, FINGERPRINTER
    )
    results = await asyncio.gather(ack(command), ack(command))
    assert results[0] == results[1]
    async with api.sessions() as session:
        assert (
            await session.scalar(select(func.count()).select_from(RequestViewAcknowledgementRecord))
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProductEventRecord)
                .where(ProductEventRecord.kind == "request.view_acknowledged")
            )
            == 1
        )
    declined = await api.decline(action(recipient, sender, value))
    page = await ListRequests(query, HASHER, codec())(
        recipient.credential, RequestBox.RECEIVED, RequestListView.RECENTLY_DECLINED
    )
    assert page.requests[0].state == RequestPublicState.PENDING_DECLINE
    assert page.requests[0].version == declined.version
    assert page.requests[0].undo_until == declined.decline_until


async def test_received_keyset_and_recent_undo_survive_more_than_twenty_newer_requests(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    oldest = await sent(api, sender, recipient)
    page_size = 20
    for _ in range(page_size):
        peer = await additional_peer(identity_engine, oldest.context.subject_id)
        await sent(api, peer, recipient)
    query = SqlRequestQueryUnitOfWork(api.sessions)
    listing = ListRequests(query, HASHER, codec())
    first = await listing(recipient.credential, RequestBox.RECEIVED)
    assert len(first.requests) == page_size
    assert first.unread_received == page_size + 1
    assert first.next_cursor is not None
    assert oldest.id not in {row.request.id for row in first.requests}
    declined = await api.decline(action(recipient, sender, oldest))
    recent = await listing(
        recipient.credential, RequestBox.RECEIVED, RequestListView.RECENTLY_DECLINED
    )
    assert [row.request.id for row in recent.requests] == [oldest.id]
    assert recent.requests[0].undo_until == declined.decline_until
    assert recent.unread_received == page_size
    detail = await ReadRequest(query, HASHER)(recipient.credential, first.requests[0].request.id)
    ack = AcknowledgeRequestViewed(
        SqlRequestViewUnitOfWork(api.sessions, record_request_viewed), HASHER, FINGERPRINTER
    )
    await ack(
        ViewRequestCommand(
            recipient.credential,
            detail.disclosure.request_id,
            detail.disclosure.id,
            IntentKey(str(uuid4())),
        )
    )
    refreshed = await listing(recipient.credential, RequestBox.RECEIVED)
    assert refreshed.unread_received == page_size - 1
    assert [row.request.id for row in refreshed.requests] == [
        row.request.id for row in first.requests
    ]
    new_peer = await additional_peer(identity_engine, oldest.context.subject_id)
    inserted = await sent(api, new_peer, recipient)
    second = await listing(recipient.credential, RequestBox.RECEIVED, cursor=first.next_cursor)
    assert [row.request.id for row in second.requests] == [oldest.id]
    assert inserted.id not in {row.request.id for row in second.requests}
    assert second.next_cursor is None


async def test_hidden_accepted_peer_masks_live_identity_without_losing_academic_history(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    value = await sent(api, sender, recipient)
    accepted = await api.accept(action(recipient, sender, value))
    visibility, _ = visibility_services(identity_engine)
    await visibility(visibility_command(recipient))
    detail = await ReadRequest(SqlRequestQueryUnitOfWork(api.sessions), HASHER)(
        sender.credential, value.id
    )
    assert detail.observation.peer.state == RequestPeerState.UNAVAILABLE
    assert detail.observation.peer.display_name is None
    assert detail.observation.peer.photo_version is None
    assert detail.observation.capabilities.can_open_conversation
    assert not detail.observation.capabilities.can_view_profile
    assert detail.observation.request.conversation_id == accepted.conversation.id
    assert detail.observation.request.context == value.context
    assert detail.observation.request.message == value.message
