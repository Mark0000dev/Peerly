from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

import studymate.infrastructure.persistence.visibility as visibility_module
from studymate.application.discovery.profiles import ReadDiscoveryProfile
from studymate.application.idempotency import IntentKey
from studymate.application.safety.blocks import ChangeBlockCommand, ChangeOwnBlock
from studymate.domain.requests.states import ConnectionRequest, RequestState
from studymate.infrastructure.persistence.blocks import SqlBlockUnitOfWork
from studymate.infrastructure.persistence.conversation_models import ConversationRecord
from studymate.infrastructure.persistence.discovery_freshness_models import DiscoveryExposureRecord
from studymate.infrastructure.persistence.discovery_profiles import SqlDiscoveryProfileUnitOfWork
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.requests.events import RequestOutcomeRecorder
from studymate.infrastructure.requests.lifecycle import close_actor_requests
from studymate.infrastructure.requests.reads import read_request
from tests.integration.profile_lifecycle_fixture import command as visibility_command
from tests.integration.profile_lifecycle_fixture import services as visibility_services
from tests.integration.requests.fixture import FINGERPRINTER, HASHER, action, prepared, sent

pytestmark = pytest.mark.integration


async def test_real_hide_closes_pending_and_old_intent_never_closes_a_new_request(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    original = await sent(api, sender, recipient)
    change, status = visibility_services(identity_engine)
    hide = visibility_command(recipient)
    hidden = await change(hide)
    async with api.sessions() as session:
        closed = await read_request(session, original.id)
        assert closed is not None
        assert closed.state == RequestState.UNAVAILABLE
        assert (
            await session.scalar(
                select(DiscoveryExposureRecord.last_activity_at).where(
                    DiscoveryExposureRecord.account_id == recipient.id
                )
            )
            == hidden.changed_at
        )
        event = await session.scalar(
            select(ProductEventRecord).where(
                ProductEventRecord.connection_request_id == original.id,
                ProductEventRecord.connection_request_state == "unavailable",
            )
        )
        assert event is not None
        assert event.request_initiator_id == recipient.id
    restored = await change(
        visibility_command(recipient, hidden=False, version=hidden.visibility_version)
    )
    new = await sent(api, sender, recipient)
    assert await change(hide) == hidden
    assert (await status(recipient.credential)).lifecycle == restored
    async with api.sessions() as session:
        current = await read_request(session, new.id)
        assert current is not None
        assert current.state == RequestState.PENDING
        previous = await read_request(session, original.id)
        assert previous is not None
        assert previous.state == RequestState.UNAVAILABLE


@pytest.mark.parametrize("incoming", [False, True])
async def test_actual_block_closes_pending_with_monotonic_parent_activity(
    identity_engine: AsyncEngine, incoming: bool
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    request = await sent(api, sender, recipient)
    blocker, target = (recipient, sender) if incoming else (sender, recipient)
    profile = await ReadDiscoveryProfile(SqlDiscoveryProfileUnitOfWork(api.sessions), HASHER)(
        blocker.credential, target.id
    )
    change = ChangeOwnBlock(SqlBlockUnitOfWork(api.sessions), HASHER, FINGERPRINTER)
    command = ChangeBlockCommand(
        blocker.credential, target.id, True, 0, IntentKey(str(uuid4())), profile.access_context.id
    )
    blocked = await change(command)
    assert await change(command) == blocked
    async with api.sessions() as session:
        closed = await read_request(session, request.id)
        assert closed is not None
        assert closed.state == RequestState.UNAVAILABLE
        assert (
            await session.scalar(
                select(DiscoveryExposureRecord.last_activity_at).where(
                    DiscoveryExposureRecord.account_id == blocker.id
                )
            )
            == blocked.changed_at
        )


async def test_accepted_conversation_is_retained_through_real_hide(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    request = await sent(api, sender, recipient)
    accepted = await api.accept(action(recipient, sender, request))
    change, _ = visibility_services(identity_engine)
    await change(visibility_command(recipient))
    async with api.sessions() as session:
        retained = await read_request(session, request.id)
        assert retained is not None
        assert retained.state == RequestState.ACCEPTED
        assert await session.get(ConversationRecord, accepted.conversation.id) is not None


async def test_failure_after_request_closure_rolls_back_parent_and_child_events(
    identity_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    request = await sent(api, sender, recipient)

    async def fail_after_closure(
        session: AsyncSession,
        account_id: UUID,
        initiator_id: UUID | None,
        recorder: RequestOutcomeRecorder,
    ) -> tuple[ConnectionRequest, ...]:
        await close_actor_requests(session, account_id, initiator_id, recorder)
        raise RuntimeError("Controlled lifecycle consequence failure")

    monkeypatch.setattr(visibility_module, "close_actor_requests", fail_after_closure)
    change, status = visibility_services(identity_engine)
    with pytest.raises(RuntimeError, match="Controlled lifecycle consequence failure"):
        await change(visibility_command(recipient))
    current = await status(recipient.credential)
    assert current.lifecycle is not None
    assert not current.lifecycle.hidden
    async with api.sessions() as session:
        original = await read_request(session, request.id)
        assert original is not None
        assert original.state == RequestState.PENDING
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProductEventRecord)
                .where(ProductEventRecord.kind == "profile.hidden")
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProductEventRecord)
                .where(ProductEventRecord.connection_request_id == request.id)
            )
            == 1
        )
