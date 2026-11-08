import asyncio
from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.requests.ports import (
    AlreadyConnected,
    ExistingOutgoing,
    IncomingRequestExists,
    RequestVersionConflictError,
    SentRequest,
)
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.requests.context import RequestText
from studymate.domain.requests.limits import (
    DAILY_SEND_LIMIT,
    OUTGOING_PENDING_LIMIT,
    RequestQuotaError,
    send_day,
)
from studymate.domain.requests.states import RequestState
from studymate.infrastructure.persistence.conversation_models import ConversationRecord
from studymate.infrastructure.persistence.discovery_pass_models import DiscoveryDecisionHeadRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.requests.models import (
    ConnectionRequestRecord,
    RequestCommandIntentRecord,
    RequestRevisionRecord,
    RequestSendDayRecord,
)
from tests.integration.requests.fixture import action, additional_peer, prepared, preview, sent

EXPECTED_TWO_REVISIONS = 2

pytestmark = pytest.mark.integration


async def test_preview_does_not_send_and_concurrent_identical_send_replays_original(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    source = await preview(api, sender, recipient)
    async with api.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ConnectionRequestRecord)) == 0
        assert await session.get(DiscoveryDecisionHeadRecord, sender.id) is None
    key = IntentKey(str(uuid4()))
    message = RequestText("Exact reviewed synthetic text")
    first, second = await asyncio.gather(
        api.send(sender.credential, recipient.id, source.id, message, key),
        api.send(sender.credential, recipient.id, source.id, message, key),
    )
    assert first == second
    assert isinstance(first, SentRequest)
    await api.withdraw(action(sender, recipient, first.request))
    assert await api.send(sender.credential, recipient.id, source.id, message, key) == first
    with pytest.raises(IdempotencyConflictError):
        await api.send(
            sender.credential, recipient.id, source.id, replace(message, note="Changed"), key
        )
    async with api.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ConnectionRequestRecord)) == 1
        assert await session.scalar(select(RequestSendDayRecord.successful_count)) == 1
        assert (
            await session.scalar(
                select(DiscoveryDecisionHeadRecord.last_sequence).where(
                    DiscoveryDecisionHeadRecord.account_id == sender.id
                )
            )
            == 1
        )


async def test_opposite_sends_resolve_one_actual_request_and_never_autoaccept(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    first_preview, second_preview = (
        await preview(api, sender, recipient),
        await preview(api, recipient, sender),
    )
    results = await asyncio.gather(
        api.send(
            sender.credential,
            recipient.id,
            first_preview.id,
            RequestText("First reviewed"),
            IntentKey(str(uuid4())),
        ),
        api.send(
            recipient.credential,
            sender.id,
            second_preview.id,
            RequestText("Opposite reviewed"),
            IntentKey(str(uuid4())),
        ),
    )
    assert sum(isinstance(value, SentRequest) for value in results) == 1
    assert sum(isinstance(value, IncomingRequestExists) for value in results) == 1
    async with api.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ConnectionRequestRecord)) == 1
        assert await session.scalar(select(func.count()).select_from(ConversationRecord)) == 0
        assert await session.scalar(select(func.sum(RequestSendDayRecord.successful_count))) == 1


async def test_acceptance_creates_real_unique_conversation_and_replays_immutable_result(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    request = await sent(api, sender, recipient)
    command = action(recipient, sender, request)
    result = await api.accept(command)
    assert result.request.state == RequestState.ACCEPTED
    assert result.conversation.request_id == request.id
    assert await api.accept(command) == result
    assert await api.preview(
        sender.credential, recipient.id, DiscoveryMode.FIND_HELP, IntentKey(str(uuid4()))
    ) == AlreadyConnected(result.conversation)
    assert await api.send(
        sender.credential,
        recipient.id,
        request.preview_id,
        RequestText("Reviewed again"),
        IntentKey(str(uuid4())),
    ) == AlreadyConnected(result.conversation)
    async with api.sessions() as session:
        conversation = (await session.scalars(select(ConversationRecord))).one()
        assert conversation.id == result.conversation.id
        assert conversation.accepted_request_version == result.request.version
        assert conversation.next_message_sequence == 1
        stored = await session.get(ConnectionRequestRecord, request.id)
        assert stored is not None
        assert stored.preview_id == request.preview_id
        assert stored.state == "accepted"


async def test_actual_conversation_and_revision_roll_back_when_canonical_boundary_fails(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    request = await sent(api, sender, recipient)
    api.recorder.fail = True
    with pytest.raises(RuntimeError, match="Synthetic canonical"):
        await api.accept(action(recipient, sender, request))
    async with api.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ConversationRecord)) == 0
        assert await session.scalar(select(func.count()).select_from(RequestRevisionRecord)) == 1
        assert (
            await session.scalar(
                select(func.count())
                .select_from(RequestCommandIntentRecord)
                .where(RequestCommandIntentRecord.operation == "accept")
            )
            == 0
        )
        assert await session.scalar(select(ConnectionRequestRecord.state)) == "pending"


async def test_pending_decline_existing_pair_and_undo_are_exact_and_not_new_sends(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    request = await sent(api, sender, recipient)
    declined = await api.decline(action(recipient, sender, request))
    assert await api.preview(
        sender.credential, recipient.id, DiscoveryMode.FIND_HELP, IntentKey(str(uuid4()))
    ) == ExistingOutgoing(declined)
    result = await api.send(
        sender.credential,
        recipient.id,
        request.preview_id,
        RequestText("Another reviewed"),
        IntentKey(str(uuid4())),
    )
    assert result == ExistingOutgoing(declined)
    command = action(recipient, sender, declined)
    undone = await api.undo(command)
    assert undone.state == RequestState.PENDING
    assert await api.undo(command) == undone
    async with api.sessions() as session:
        assert await session.scalar(select(RequestSendDayRecord.successful_count)) == 1
        assert await session.scalar(select(func.count()).select_from(ConversationRecord)) == 0


async def test_five_pending_race_across_distinct_real_peers_never_overspends(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    first = await preview(api, sender, recipient)
    peers = [recipient]
    peers.extend(
        [
            await additional_peer(identity_engine, first.context.subject_id)
            for _ in range(OUTGOING_PENDING_LIMIT)
        ]
    )
    previews = [first, *(await asyncio.gather(*(preview(api, sender, peer) for peer in peers[1:])))]
    results = await asyncio.gather(
        *(
            api.send(
                sender.credential,
                peer.id,
                snapshot.id,
                RequestText("Explicit reviewed quota intent"),
                IntentKey(str(uuid4())),
            )
            for peer, snapshot in zip(peers, previews, strict=True)
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(result, SentRequest) for result in results) == OUTGOING_PENDING_LIMIT
    assert sum(isinstance(result, RequestQuotaError) for result in results) == 1
    async with api.sessions() as session:
        assert (
            await session.scalar(select(func.count()).select_from(ConnectionRequestRecord))
            == OUTGOING_PENDING_LIMIT
        )
        assert (
            await session.scalar(select(RequestSendDayRecord.successful_count))
            == OUTGOING_PENDING_LIMIT
        )
        assert (
            await session.scalar(
                select(DiscoveryDecisionHeadRecord.last_sequence).where(
                    DiscoveryDecisionHeadRecord.account_id == sender.id
                )
            )
            == OUTGOING_PENDING_LIMIT
        )


async def test_ten_successful_sends_are_not_refunded_by_withdrawal_and_day_is_kl_date(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    first = await preview(api, sender, recipient)
    peer = recipient
    for number in range(DAILY_SEND_LIMIT):
        request = await sent(api, sender, peer)
        await api.withdraw(action(sender, peer, request))
        if number < DAILY_SEND_LIMIT - 1:
            peer = await additional_peer(identity_engine, first.context.subject_id)
    another = await additional_peer(identity_engine, first.context.subject_id)
    snapshot = await preview(api, sender, another)
    with pytest.raises(RequestQuotaError):
        await api.send(
            sender.credential,
            another.id,
            snapshot.id,
            RequestText("Eleventh explicit reviewed intent"),
            IntentKey(str(uuid4())),
        )
    async with api.sessions() as session:
        assert (
            await session.scalar(select(func.count()).select_from(ConnectionRequestRecord))
            == DAILY_SEND_LIMIT
        )
        counter = (await session.scalars(select(RequestSendDayRecord))).one()
        requests = tuple(await session.scalars(select(ConnectionRequestRecord)))
        assert counter.successful_count == DAILY_SEND_LIMIT
        assert all(counter.local_day == send_day(row.sent_at) for row in requests)
        assert all(row.state == "withdrawn" for row in requests)


async def test_accept_withdraw_race_commits_one_real_terminal_source_and_no_orphan_conversation(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    request = await sent(api, sender, recipient)
    results = await asyncio.gather(
        api.withdraw(action(sender, recipient, request)),
        api.accept(action(recipient, sender, request)),
        return_exceptions=True,
    )
    assert sum(isinstance(result, RequestVersionConflictError) for result in results) == 1
    async with api.sessions() as session:
        stored = await session.get(ConnectionRequestRecord, request.id)
        assert stored is not None
        conversations = tuple(await session.scalars(select(ConversationRecord)))
        if stored.state == "accepted":
            assert len(conversations) == 1
            assert conversations[0].request_id == request.id
        else:
            assert stored.state == "withdrawn"
            assert not conversations
        events = tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "request.changed")
            )
        )
        assert len(events) == EXPECTED_TWO_REVISIONS
        assert {event.connection_request_version for event in events} == {1, 2}


async def test_cancellation_before_commit_rolls_back_send_counter_head_and_actual_event(
    identity_engine: AsyncEngine,
) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession

    from studymate.application.requests.send import SendRequest
    from studymate.domain.requests.states import ConnectionRequest
    from studymate.infrastructure.requests.transactions import SqlRequestUnitOfWork
    from tests.integration.requests.fixture import FINGERPRINTER, HASHER

    sender, recipient, api = await prepared(identity_engine)
    source = await preview(api, sender, recipient)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def paused_canonical(
        session: AsyncSession, request: ConnectionRequest, initiator_id: UUID | None
    ) -> None:
        await api.recorder(session, request, initiator_id)
        entered.set()
        await release.wait()

    send = SendRequest(SqlRequestUnitOfWork(api.sessions, paused_canonical), HASHER, FINGERPRINTER)
    intent = IntentKey(str(uuid4()))
    message = RequestText("Original reviewed cancellation intent")
    task = asyncio.create_task(send(sender.credential, recipient.id, source.id, message, intent))
    await asyncio.wait_for(entered.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with api.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ConnectionRequestRecord)) == 0
        assert await session.scalar(select(func.count()).select_from(RequestSendDayRecord)) == 0
        assert await session.get(DiscoveryDecisionHeadRecord, sender.id) is None
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProductEventRecord)
                .where(ProductEventRecord.kind == "request.changed")
            )
            == 0
        )
    original = await api.send(sender.credential, recipient.id, source.id, message, intent)
    assert await api.send(sender.credential, recipient.id, source.id, message, intent) == original
    async with api.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ConnectionRequestRecord)) == 1
        assert await session.scalar(select(RequestSendDayRecord.successful_count)) == 1


@pytest.mark.parametrize("reverse", [False, True])
async def test_existing_pair_intent_replays_original_pending_decline_after_undo(
    identity_engine: AsyncEngine, reverse: bool
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    viewer, target = (recipient, sender) if reverse else (sender, recipient)
    source = await preview(api, viewer, target)
    first = await sent(api, sender, recipient)
    declining = await api.decline(action(recipient, sender, first))
    intent = IntentKey(str(uuid4()))
    message = RequestText("Reviewed existing pair intent")
    original = await api.send(viewer.credential, target.id, source.id, message, intent)
    assert isinstance(original, IncomingRequestExists if reverse else ExistingOutgoing)
    undone = await api.undo(action(recipient, sender, declining))
    assert undone.state == RequestState.PENDING
    assert await api.send(viewer.credential, target.id, source.id, message, intent) == original
    async with api.sessions() as session:
        assert await session.scalar(select(RequestSendDayRecord.successful_count)) == 1
        assert (
            await session.scalar(select(ConnectionRequestRecord.current_version)) == undone.version
        )
