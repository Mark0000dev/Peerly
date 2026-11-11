from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

import studymate.infrastructure.persistence.goals as goal_module
from studymate.application.idempotency import IntentKey
from studymate.application.profiles.goals import (
    CompleteGoalCommand,
    CompleteOwnGoal,
    ReadOwnGoal,
    SaveGoalCommand,
    SaveOwnGoal,
)
from studymate.application.requests.ports import RequestPreview, SentRequest
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.requests.context import RequestText
from studymate.domain.requests.states import ConnectionRequest, RequestState
from studymate.infrastructure.persistence.goal_models import GoalIntentRecord
from studymate.infrastructure.persistence.goals import SqlGoalUnitOfWork
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.requests.events import RequestOutcomeRecorder
from studymate.infrastructure.requests.lifecycle import close_goal_requests
from studymate.infrastructure.requests.reads import read_request
from tests.integration.requests.fixture import FINGERPRINTER, HASHER, Services, prepared, sent
from tests.integration.student_actor import Actor

pytestmark = pytest.mark.integration


async def complete_command(api: Services, owner: Actor) -> CompleteGoalCommand:
    current = await ReadOwnGoal(SqlGoalUnitOfWork(api.sessions), HASHER)(owner.credential)
    assert current is not None
    return CompleteGoalCommand(
        owner.credential, current.goal.id, current.goal.version, IntentKey(str(uuid4()))
    )


@pytest.mark.parametrize("incoming_offer", [False, True])
async def test_actual_goal_done_closes_owned_pending_source_in_same_transaction(
    identity_engine: AsyncEngine, incoming_offer: bool
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    mode = DiscoveryMode.OFFER_HELP if incoming_offer else DiscoveryMode.FIND_HELP
    preview = await api.preview(sender.credential, recipient.id, mode, IntentKey(str(uuid4())))
    assert isinstance(preview, RequestPreview)
    result = await api.send(
        sender.credential,
        recipient.id,
        preview.id,
        RequestText("Explicit source-bound goal request"),
        IntentKey(str(uuid4())),
    )
    assert isinstance(result, SentRequest)
    owner = recipient if incoming_offer else sender
    command = await complete_command(api, owner)
    service = CompleteOwnGoal(SqlGoalUnitOfWork(api.sessions), HASHER, FINGERPRINTER)
    completed = await service(command)
    assert not completed.goal.active
    async with api.sessions() as session:
        current = await read_request(session, result.request.id)
        assert current is not None
        assert current.state == RequestState.UNAVAILABLE
        assert current.context == result.request.context
        event = await session.scalar(
            select(ProductEventRecord).where(
                ProductEventRecord.connection_request_id == current.id,
                ProductEventRecord.connection_request_version == current.version,
            )
        )
        assert event is not None
        assert event.request_initiator_id == owner.id


async def test_done_intent_replay_does_not_close_new_goal_request(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    original = await sent(api, sender, recipient)
    goals = SqlGoalUnitOfWork(api.sessions)
    before = await ReadOwnGoal(goals, HASHER)(sender.credential)
    assert before is not None
    command = await complete_command(api, sender)
    service = CompleteOwnGoal(goals, HASHER, FINGERPRINTER)
    completed = await service(command)
    await SaveOwnGoal(goals, HASHER, FINGERPRINTER)(
        SaveGoalCommand(sender.credential, before.goal.content, None, 0, IntentKey(str(uuid4())))
    )
    fresh = await sent(api, sender, recipient)
    assert await service(command) == completed
    async with api.sessions() as session:
        old = await read_request(session, original.id)
        current = await read_request(session, fresh.id)
        assert old is not None
        assert old.state == RequestState.UNAVAILABLE
        assert current is not None
        assert current.state == RequestState.PENDING


async def test_failure_after_goal_pending_closure_rolls_back_goal_request_receipts_and_events(
    identity_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    request = await sent(api, sender, recipient)
    goals = SqlGoalUnitOfWork(api.sessions)
    original_goal = await ReadOwnGoal(goals, HASHER)(sender.credential)
    command = await complete_command(api, sender)

    async def fail_after_closure(
        session: AsyncSession,
        account_id: UUID,
        goal_id: UUID,
        initiator_id: UUID | None,
        recorder: RequestOutcomeRecorder,
    ) -> tuple[ConnectionRequest, ...]:
        await close_goal_requests(session, account_id, goal_id, initiator_id, recorder)
        raise RuntimeError("Controlled parent goal closure failure")

    monkeypatch.setattr(goal_module, "close_goal_requests", fail_after_closure)
    with pytest.raises(RuntimeError, match="Controlled parent goal closure failure"):
        await CompleteOwnGoal(goals, HASHER, FINGERPRINTER)(command)
    assert await ReadOwnGoal(goals, HASHER)(sender.credential) == original_goal
    async with api.sessions() as session:
        current = await read_request(session, request.id)
        assert current == request
        assert await session.get(GoalIntentRecord, (sender.id, command.intent_key.value)) is None
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProductEventRecord)
                .where(ProductEventRecord.kind == "goal.completed")
            )
            == 0
        )
