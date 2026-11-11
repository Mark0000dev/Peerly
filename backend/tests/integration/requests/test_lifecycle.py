import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.idempotency import IntentKey
from studymate.application.requests.expiry import ExpireRequests
from studymate.application.requests.ports import (
    RequestCooldownError,
    SentRequest,
)
from studymate.domain.relationships import AccountPair
from studymate.domain.requests.context import RequestText
from studymate.domain.requests.states import RequestState, RequestUnavailableError
from studymate.infrastructure.persistence.discovery_freshness_models import DiscoveryExposureRecord
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.requests.expiry import SqlRequestExpiryUnitOfWork
from studymate.infrastructure.requests.lifecycle import close_actor_requests, close_pair_requests
from studymate.infrastructure.requests.models import ConnectionRequestRecord, RequestSendDayRecord
from tests.integration.requests.fixture import action, additional_peer, prepared, preview, sent

pytestmark = pytest.mark.integration
EXPECTED_DECLINE_HISTORY = 3


async def test_real_ten_second_finality_system_expiry_does_not_warm_either_participant(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    request = await sent(api, sender, recipient)
    declined = await api.decline(action(recipient, sender, request))
    assert declined.decline_until is not None
    async with api.sessions() as session:
        before = {
            owner: await session.scalar(
                select(DiscoveryExposureRecord.last_activity_at).where(
                    DiscoveryExposureRecord.account_id == owner
                )
            )
            for owner in (sender.id, recipient.id)
        }
    # Actual production ten-second window, not a reduced fixture/production budget.
    async with api.sessions() as session:
        database_now = await SqlIdentityTransaction(session).now()
    await asyncio.sleep(max(0.0, (declined.decline_until - database_now).total_seconds()) + 0.05)
    with pytest.raises(RequestUnavailableError):
        await api.undo(action(recipient, sender, declined))
    expiry = ExpireRequests(SqlRequestExpiryUnitOfWork(api.sessions, api.recorder))
    results = await expiry()
    assert len(results) == 1
    final = results[0]
    assert final.state == RequestState.DECLINED
    assert final.changed_at == declined.decline_until
    assert await expiry() == ()
    async with api.sessions() as session:
        after = {
            owner: await session.scalar(
                select(DiscoveryExposureRecord.last_activity_at).where(
                    DiscoveryExposureRecord.account_id == owner
                )
            )
            for owner in (sender.id, recipient.id)
        }
        assert after == before
        events = tuple(
            await session.scalars(
                select(ProductEventRecord)
                .where(ProductEventRecord.kind == "request.changed")
                .order_by(ProductEventRecord.connection_request_version)
            )
        )
        assert len(events) == EXPECTED_DECLINE_HISTORY
        assert [event.request_initiator_id for event in events] == [sender.id, recipient.id, None]
        assert all(event.account_id == sender.id for event in events)
        assert events[-1].occurred_at == declined.decline_until
        assert await session.scalar(select(RequestSendDayRecord.successful_count)) == 1
    with pytest.raises(RequestCooldownError):
        await preview(api, sender, recipient)
    with pytest.raises(RequestCooldownError):
        await api.send(
            sender.credential,
            recipient.id,
            request.preview_id,
            RequestText("Reviewed after decline"),
            IntentKey(str(uuid4())),
        )
    reverse = await preview(api, recipient, sender)
    assert isinstance(
        await api.send(
            recipient.credential,
            sender.id,
            reverse.id,
            RequestText("Recipient explicitly initiates"),
            IntentKey(str(uuid4())),
        ),
        SentRequest,
    )


async def test_single_actor_lifecycle_closes_both_directions_and_rolls_back_together(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    first = await sent(api, sender, recipient)
    other = await additional_peer(identity_engine, first.context.subject_id)
    second = await sent(api, other, sender)

    async def close(rollback: bool) -> None:
        async with api.sessions.begin() as session:
            await session.execute(
                select(AccountRecord.id).where(AccountRecord.id == sender.id).with_for_update()
            )
            closed = await close_actor_requests(session, sender.id, sender.id, api.recorder)
            assert {value.id for value in closed} == {first.id, second.id}
            assert all(value.state == RequestState.UNAVAILABLE for value in closed)
            if rollback:
                raise RuntimeError("Synthetic lifecycle rollback")

    with pytest.raises(RuntimeError, match="Synthetic lifecycle"):
        await close(True)
    async with api.sessions() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ConnectionRequestRecord)
                .where(ConnectionRequestRecord.state == "pending")
            )
            == EXPECTED_BOTH_DIRECTIONS
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProductEventRecord)
                .where(ProductEventRecord.kind == "request.changed")
            )
            == EXPECTED_BOTH_DIRECTIONS
        )
    await close(False)
    async with api.sessions.begin() as session:
        await session.execute(
            select(AccountRecord.id).where(AccountRecord.id == sender.id).with_for_update()
        )
        assert await close_actor_requests(session, sender.id, sender.id, api.recorder) == ()
    async with api.sessions() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ConnectionRequestRecord)
                .where(ConnectionRequestRecord.state == "unavailable")
            )
            == EXPECTED_BOTH_DIRECTIONS
        )
        assert (
            await session.scalar(select(func.sum(RequestSendDayRecord.successful_count)))
            == EXPECTED_BOTH_DIRECTIONS
        )


async def test_pair_closure_uses_existing_relationship_and_leaves_history_retained(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    pair = AccountPair.between(sender.id, recipient.id)
    async with api.sessions.begin() as session:
        await session.execute(
            select(AccountRecord.id)
            .where(AccountRecord.id.in_((pair.low, pair.high)))
            .order_by(AccountRecord.id)
            .with_for_update(key_share=True)
        )
        assert await close_pair_requests(session, pair, None, api.recorder) == ()
    request = await sent(api, sender, recipient)
    async with api.sessions.begin() as session:
        await session.execute(
            select(AccountRecord.id)
            .where(AccountRecord.id.in_((pair.low, pair.high)))
            .order_by(AccountRecord.id)
            .with_for_update(key_share=True)
        )
        closed = await close_pair_requests(session, pair, recipient.id, api.recorder)
        assert len(closed) == 1
        assert closed[0].id == request.id
    async with api.sessions.begin() as session:
        await session.execute(
            select(AccountRecord.id)
            .where(AccountRecord.id.in_((pair.low, pair.high)))
            .order_by(AccountRecord.id)
            .with_for_update(key_share=True)
        )
        assert await close_pair_requests(session, pair, recipient.id, api.recorder) == ()
    async with api.sessions() as session:
        assert (
            await session.scalar(select(ConnectionRequestRecord.request_text))
            == request.message.text
        )
        event = (
            await session.scalars(
                select(ProductEventRecord).where(
                    ProductEventRecord.kind == "request.changed",
                    ProductEventRecord.connection_request_version == closed[0].version,
                )
            )
        ).one()
        assert event.request_initiator_id == recipient.id


EXPECTED_BOTH_DIRECTIONS = 2
