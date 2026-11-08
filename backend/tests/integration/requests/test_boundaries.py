from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.discovery.passes import ChangePassCommand, PassUndoUnavailableError
from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import require_verified_student
from studymate.application.profiles.goals import ReadOwnGoal, SaveGoalCommand, SaveOwnGoal
from studymate.application.requests.ports import (
    AlreadyConnected,
    RequestPreview,
    RequestSourceChangedError,
    SentRequest,
)
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.discovery_context import discovery_context
from studymate.domain.requests.context import RequestText
from studymate.domain.requests.states import RequestUnavailableError
from studymate.infrastructure.persistence.goals import SqlGoalUnitOfWork
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.requests.codec import StoredRequestSnapshotError
from studymate.infrastructure.requests.models import ConnectionRequestRecord, RequestPreviewRecord
from studymate.infrastructure.requests.transactions import SqlRequestUnitOfWork
from tests.integration.catalogue_fixture import subject
from tests.integration.profile_lifecycle_fixture import command as visibility_command
from tests.integration.profile_lifecycle_fixture import services as visibility_services
from tests.integration.requests.fixture import (
    FINGERPRINTER,
    HASHER,
    action,
    prepared,
    preview,
    sent,
)
from tests.integration.test_discovery_passes import service as pass_service

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("mode", list(DiscoveryMode))
async def test_all_mode_snapshots_bind_actual_owned_sources_and_replay_preview(
    identity_engine: AsyncEngine, mode: DiscoveryMode
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    key = IntentKey(str(uuid4()))
    first = await api.preview(sender.credential, recipient.id, mode, key)
    assert isinstance(first, RequestPreview)
    assert await api.preview(sender.credential, recipient.id, mode, key) == first
    async with api.sessions() as session:
        row = await session.get(RequestPreviewRecord, first.id)
        assert row is not None
        assert row.sender_id == sender.id
        assert row.recipient_id == recipient.id
        assert row.mode == mode.value
    request = await api.send(
        sender.credential,
        recipient.id,
        first.id,
        RequestText("Explicit reviewed mode context"),
        IntentKey(str(uuid4())),
    )
    assert isinstance(request, SentRequest)
    assert request.request.context == first.context


async def test_existing_conversation_is_recovered_from_owned_history_while_peer_hidden(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    request = await sent(api, sender, recipient)
    accepted = await api.accept(action(recipient, sender, request))
    visibility, _ = visibility_services(identity_engine)
    await visibility(visibility_command(recipient))
    result = await api.send(
        sender.credential,
        recipient.id,
        request.preview_id,
        RequestText("Reviewed recovery, no new send"),
        IntentKey(str(uuid4())),
    )
    assert result == AlreadyConnected(accepted.conversation)


async def test_subject_column_or_expiry_corruption_fails_closed_without_private_errors(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    request = await sent(api, sender, recipient)
    extra = await subject(identity_engine, name="Other synthetic subject", aliases=())
    async with api.sessions.begin() as session:
        await session.execute(
            update(RequestPreviewRecord)
            .where(RequestPreviewRecord.id == request.preview_id)
            .values(subject_id=extra.id)
        )
    with pytest.raises(StoredRequestSnapshotError, match="owned references") as failed:
        await api.withdraw(action(sender, recipient, request))
    assert "Private" not in str(failed.value)
    async with api.sessions.begin() as session:
        await session.execute(
            update(RequestPreviewRecord)
            .where(RequestPreviewRecord.id == request.preview_id)
            .values(subject_id=request.context.subject_id)
        )
        await session.execute(
            update(ConnectionRequestRecord)
            .where(ConnectionRequestRecord.id == request.id)
            .values(expires_at=request.expires_at + timedelta(days=1))
        )
    with pytest.raises(StoredRequestSnapshotError, match="deadline or pair"):
        await api.withdraw(action(sender, recipient, request))


async def test_adapter_authority_scope_and_foreign_preview_cannot_be_bypassed(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    opposite = await preview(api, recipient, sender)
    uow = SqlRequestUnitOfWork(api.sessions, api.recorder)
    async with uow.transaction(recipient.id) as transaction:
        with pytest.raises(RuntimeError, match="authenticated actor"):
            transaction.actor_id()
        await require_verified_student(transaction, await HASHER.digest(sender.credential))
        with pytest.raises(RuntimeError, match="differs"):
            transaction.check_actor(recipient.id)
        with pytest.raises(RuntimeError, match="peer differs"):
            await transaction.pair_state(sender.id, uuid4(), await transaction.now())
        assert await transaction.preview(opposite.id) is None
        with pytest.raises(RuntimeError, match="another actors"):
            await transaction.save_preview(opposite)
        assert await transaction.request(uuid4()) is None
    async with uow.transaction(sender.id) as transaction:
        await require_verified_student(transaction, await HASHER.digest(sender.credential))
        with pytest.raises(RequestUnavailableError):
            transaction.pair()


async def test_actual_send_invalidates_previous_discovery_pass_undo_but_preview_does_not(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    uow = SqlGoalUnitOfWork(api.sessions)
    goal = await ReadOwnGoal(uow, HASHER)(sender.credential)
    assert goal is not None
    context = discovery_context(sender.id, DiscoveryMode.FIND_HELP, goal.goal, None)
    assert context is not None
    change = pass_service(identity_engine)
    command = ChangePassCommand(
        sender.credential, context.scope, recipient.id, True, 0, IntentKey(str(uuid4()))
    )
    passed = await change(command)
    await preview(api, sender, recipient)
    await sent(api, sender, recipient)
    with pytest.raises(PassUndoUnavailableError):
        await change(
            replace(
                command,
                passed=False,
                undo=True,
                expected_version=passed.version,
                intent_key=IntentKey(str(uuid4())),
            )
        )


async def test_postsend_source_edit_keeps_original_conversation_context_and_presend_edit_rejects(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    source = await preview(api, sender, recipient)
    goal_uow = SqlGoalUnitOfWork(api.sessions)
    current = await ReadOwnGoal(goal_uow, HASHER)(sender.credential)
    assert current is not None
    save = SaveOwnGoal(goal_uow, HASHER, FINGERPRINTER)
    changed = await save(
        SaveGoalCommand(
            sender.credential,
            replace(current.goal.content, context="Changed before send"),
            current.goal.id,
            current.goal.version,
            IntentKey(str(uuid4())),
        )
    )
    with pytest.raises(RequestSourceChangedError):
        await api.send(
            sender.credential,
            recipient.id,
            source.id,
            RequestText("Reviewed old source"),
            IntentKey(str(uuid4())),
        )
    request = await sent(api, sender, recipient)
    await save(
        SaveGoalCommand(
            sender.credential,
            replace(changed.goal.content, context="Changed after send"),
            changed.goal.id,
            changed.goal.version,
            IntentKey(str(uuid4())),
        )
    )
    accepted = await api.accept(action(recipient, sender, request))
    assert accepted.request.context == request.context
    assert accepted.request.context.sender_goal is not None
    assert accepted.request.context.sender_goal.goal.content.context == "Changed before send"


async def test_deferred_current_revision_constraint_rejects_fake_acceptance_at_commit(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    request = await sent(api, sender, recipient)

    async def fake_acceptance() -> None:
        async with api.sessions.begin() as session:
            await session.execute(
                update(ConnectionRequestRecord)
                .where(ConnectionRequestRecord.id == request.id)
                .values(state="accepted", current_version=2)
            )

    with pytest.raises(IntegrityError):
        await fake_acceptance()
    async with api.sessions() as session:
        events = tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "request.changed")
            )
        )
        assert len(events) == 1
        assert events[0].connection_request_state == "pending"
