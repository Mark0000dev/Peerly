from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.idempotency import IntentKey
from studymate.application.profiles.goals import ReadOwnGoal, SaveGoalCommand, SaveOwnGoal
from studymate.application.requests.ports import RequestPreview, SentRequest
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.requests.context import RequestText
from studymate.domain.requests.states import ConnectionRequest, RequestState
from studymate.infrastructure.persistence.goals import SqlGoalUnitOfWork
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.requests.lifecycle import close_goal_requests
from studymate.infrastructure.requests.models import ConnectionRequestRecord
from studymate.infrastructure.requests.reads import read_request
from tests.integration.requests.fixture import (
    FINGERPRINTER,
    HASHER,
    Services,
    action,
    additional_peer,
    prepared,
    sent,
)
from tests.integration.student_actor import Actor

pytestmark = pytest.mark.integration


async def send_mode(
    api: Services, sender: Actor, recipient: Actor, mode: DiscoveryMode
) -> ConnectionRequest:
    preview = await api.preview(sender.credential, recipient.id, mode, IntentKey(str(uuid4())))
    assert isinstance(preview, RequestPreview)
    result = await api.send(
        sender.credential,
        recipient.id,
        preview.id,
        RequestText("Reviewed goal-specific intent"),
        IntentKey(str(uuid4())),
    )
    assert isinstance(result, SentRequest)
    return result.request


async def close_owned(
    api: Services, owner_id: UUID, goal_id: UUID
) -> tuple[ConnectionRequest, ...]:
    async with api.sessions.begin() as session:
        await session.execute(
            select(AccountRecord.id).where(AccountRecord.id == owner_id).with_for_update()
        )
        return await close_goal_requests(session, owner_id, goal_id, owner_id, api.recorder)


@pytest.mark.parametrize(
    ("mode", "recipient_owner"),
    [
        (DiscoveryMode.FIND_HELP, False),
        (DiscoveryMode.OFFER_HELP, True),
        (DiscoveryMode.STUDY_TOGETHER, False),
        (DiscoveryMode.STUDY_TOGETHER, True),
    ],
)
async def test_completed_goal_closes_each_actual_owned_source_including_incoming_offers(
    identity_engine: AsyncEngine,
    mode: DiscoveryMode,
    recipient_owner: bool,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    pending = await send_mode(api, sender, recipient, mode)
    declined = await api.decline(action(recipient, sender, pending))
    owner = recipient if recipient_owner else sender
    source = pending.context.recipient_goal if recipient_owner else pending.context.sender_goal
    assert source is not None
    assert await close_owned(api, owner.id, uuid4()) == ()
    closed = await close_owned(api, owner.id, source.goal.id)
    assert len(closed) == 1
    assert closed[0].id == pending.id
    assert closed[0].state == RequestState.UNAVAILABLE
    assert closed[0].version == declined.version + 1
    assert closed[0].context == pending.context
    assert closed[0].message == pending.message
    assert await close_owned(api, owner.id, source.goal.id) == ()
    async with api.sessions() as session:
        events = tuple(
            await session.scalars(
                select(ProductEventRecord)
                .where(ProductEventRecord.kind == "request.changed")
                .order_by(ProductEventRecord.connection_request_version)
            )
        )
        assert events[-1].request_initiator_id == owner.id
        assert events[-1].connection_request_state == "unavailable"


async def test_goal_closure_matches_old_versions_but_keeps_accepted_and_unrelated_help(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    pending = await sent(api, sender, recipient)
    source = pending.context.sender_goal
    assert source is not None
    uow = SqlGoalUnitOfWork(api.sessions)
    current = await ReadOwnGoal(uow, HASHER)(sender.credential)
    assert current is not None
    edited = await SaveOwnGoal(uow, HASHER, FINGERPRINTER)(
        SaveGoalCommand(
            sender.credential,
            replace(current.goal.content, topic="Deliberately revised topic"),
            current.goal.id,
            current.goal.version,
            IntentKey(str(uuid4())),
        )
    )
    assert edited.goal.version > source.goal.version
    offering_peer = await additional_peer(identity_engine, pending.context.subject_id)
    incoming_offer = await send_mode(api, offering_peer, sender, DiscoveryMode.OFFER_HELP)
    assert incoming_offer.context.recipient_goal is not None
    assert incoming_offer.context.recipient_goal.goal.version == edited.goal.version
    peer = await additional_peer(identity_engine, pending.context.subject_id)
    accepted_source = await sent(api, sender, peer)
    accepted = await api.accept(action(peer, sender, accepted_source))
    other = await additional_peer(identity_engine, pending.context.subject_id)
    unrelated = await send_mode(api, sender, other, DiscoveryMode.OFFER_HELP)
    # The sender's help, rather than sender's goal, is the actual source here.
    assert unrelated.context.sender_goal is None
    assert await close_owned(api, recipient.id, source.goal.id) == ()
    closed = await close_owned(api, sender.id, source.goal.id)
    assert {value.id for value in closed} == {pending.id, incoming_offer.id}
    async with api.sessions() as session:
        stored_accepted = await read_request(session, accepted_source.id)
        stored_unrelated = await read_request(session, unrelated.id)
        assert stored_accepted == accepted.request
        assert stored_accepted.conversation_id == accepted.conversation.id
        assert stored_unrelated == unrelated


async def test_goal_closure_canonical_failure_rolls_back_all_request_history(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    pending = await sent(api, sender, recipient)
    source = pending.context.sender_goal
    assert source is not None
    peer = await additional_peer(identity_engine, pending.context.subject_id)
    second = await sent(api, sender, peer)
    api.recorder.fail = True
    with pytest.raises(RuntimeError, match="canonical boundary"):
        await close_owned(api, sender.id, source.goal.id)
    api.recorder.fail = False
    expected_initial = {pending.id, second.id}
    async with api.sessions() as session:
        assert await read_request(session, pending.id) == pending
        assert await read_request(session, second.id) == second
        assert await session.scalar(
            select(func.count())
            .select_from(ProductEventRecord)
            .where(ProductEventRecord.kind == "request.changed")
        ) == len(expected_initial)
        assert await session.scalar(
            select(func.count()).select_from(ConnectionRequestRecord)
        ) == len(expected_initial)
    closed = await close_owned(api, sender.id, source.goal.id)
    assert {value.id for value in closed} == expected_initial
    assert all(value.state == RequestState.UNAVAILABLE for value in closed)
