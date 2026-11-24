"""Real PostgreSQL boundaries; requires proposed migration and registry integration."""

import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.student_notifications.worker import DeliverNextStudentNotification
from studymate.domain.student_notifications.delivery import Kind, Outcome, State
from studymate.infrastructure.student_notifications.models import DeliveryRecord
from studymate.infrastructure.student_notifications.queue import SqlStudentNotifications, clock
from tests.integration.lifecycle.test_deletion_transactions import command_for
from tests.integration.lifecycle.test_real_effects import deletion
from tests.integration.profile_lifecycle_fixture import command as visibility_command
from tests.integration.profile_lifecycle_fixture import services as visibility_services
from tests.integration.requests.fixture import action, prepared, sent
from tests.integration.test_message_commands import chat
from tests.unit.student_notifications.test_worker import Transport

pytestmark = pytest.mark.integration


def queue(engine: AsyncEngine) -> SqlStudentNotifications:
    return SqlStudentNotifications(async_sessionmaker(engine, expire_on_commit=False))


async def test_real_request_acceptance_and_message_sources_are_distinct_and_idempotent(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    notifications = queue(identity_engine)
    await notifications.activate()
    request = await sent(api, sender, recipient)
    assert await notifications.materialize() == 1
    assert await notifications.materialize() == 0
    claim = await notifications.claim()
    assert claim is not None
    assert claim.delivery.recipient_id == recipient.id
    assert claim.delivery.kind == Kind.REQUEST
    assert await notifications.authorize(claim) is not None
    assert await notifications.finish(claim, Outcome.ACCEPTED)
    await api.accept(action(recipient, sender, request))
    assert await notifications.materialize() == 1
    accepted = await notifications.claim()
    assert accepted is not None
    assert accepted.delivery.recipient_id == sender.id
    assert accepted.delivery.kind == Kind.ACCEPTED_CONNECTION
    assert await notifications.authorize(accepted) is not None
    assert await notifications.finish(accepted, Outcome.ACCEPTED)


async def test_real_consumer_and_claim_races_have_one_logical_recipient_delivery(
    identity_engine: AsyncEngine,
) -> None:
    thread = await chat(identity_engine)
    notifications = queue(identity_engine)
    await notifications.activate()
    await thread.send()(thread.command())
    counts = await asyncio.gather(notifications.materialize(), notifications.materialize())
    assert sum(counts) == 1
    claims = await asyncio.gather(notifications.claim(), notifications.claim())
    actual = [claim for claim in claims if claim is not None]
    assert len(actual) == 1
    assert actual[0].delivery.recipient_id == thread.recipient.id
    assert await notifications.authorize(actual[0]) is not None
    assert await notifications.authorize(actual[0]) is None
    assert await notifications.finish(actual[0], Outcome.ACCEPTED)
    assert not await notifications.finish(actual[0], Outcome.ACCEPTED)


async def test_hidden_profile_existing_chat_still_delivers_fixed_private_free_preview(
    identity_engine: AsyncEngine,
) -> None:
    thread = await chat(identity_engine)
    notifications = queue(identity_engine)
    await notifications.activate()
    change, _ = visibility_services(identity_engine)
    await change(visibility_command(thread.recipient))
    await thread.send()(thread.command())
    assert await notifications.materialize() == 1
    provider = Transport()
    assert await DeliverNextStudentNotification(notifications, provider)()
    assert len(provider.calls) == 1
    assert provider.calls[0].preview == "New message about your study request"
    assert "Synthetic private message" not in repr(provider.calls)


async def test_real_deletion_between_enqueue_and_dispatch_cancels_without_provider(
    identity_engine: AsyncEngine,
) -> None:
    thread = await chat(identity_engine)
    notifications = queue(identity_engine)
    await notifications.activate()
    await thread.send()(thread.command())
    assert await notifications.materialize() == 1
    async with notifications.sessions() as session:
        pending = (await session.scalars(select(DeliveryRecord))).one()
        assert pending.state == State.PENDING.value
        source = (
            pending.id,
            pending.event_id,
            pending.actor_id,
            pending.recipient_id,
            pending.relationship_id,
        )
    await deletion(identity_engine)(await command_for(identity_engine, thread.recipient))
    # A new transaction observes retirement committed by deletion, before dispatch.
    async with notifications.sessions() as session:
        cancelled = (await session.scalars(select(DeliveryRecord))).one()
        assert cancelled.state == State.CANCELLED.value
        assert cancelled.lease_token is None
        assert cancelled.lease_until is None
        assert cancelled.attempts == 0
        assert (
            cancelled.id,
            cancelled.event_id,
            cancelled.actor_id,
            cancelled.recipient_id,
            cancelled.relationship_id,
        ) == source
    provider = Transport()
    assert not await DeliverNextStudentNotification(notifications, provider)()
    assert provider.calls == []
    async with notifications.sessions() as session:
        assert await session.scalar(select(DeliveryRecord.state)) == State.CANCELLED.value


async def test_real_expired_claim_is_fenced_and_expired_sending_never_replays(
    identity_engine: AsyncEngine,
) -> None:
    thread = await chat(identity_engine)
    notifications = queue(identity_engine)
    await notifications.activate()
    await thread.send()(thread.command())
    assert await notifications.materialize() == 1
    original = await notifications.claim()
    assert original is not None
    async with notifications.sessions.begin() as session:
        await session.execute(
            update(DeliveryRecord).values(lease_until=await clock(session) - timedelta(seconds=1))
        )
    replacement = await notifications.claim()
    assert replacement is not None
    assert replacement.token != original.token
    assert await notifications.authorize(original) is None
    assert await notifications.authorize(replacement) is not None
    async with notifications.sessions.begin() as session:
        await session.execute(
            update(DeliveryRecord).values(lease_until=await clock(session) - timedelta(seconds=1))
        )
    assert await notifications.claim() is None
    assert not await notifications.finish(replacement, Outcome.ACCEPTED)
    async with notifications.sessions() as session:
        assert await session.scalar(select(DeliveryRecord.state)) == State.UNKNOWN.value


async def test_pre_activation_history_not_blasted_and_unknown_does_not_repeat(
    identity_engine: AsyncEngine,
) -> None:
    thread = await chat(identity_engine)
    notifications = queue(identity_engine)
    await thread.send()(thread.command())
    await notifications.activate()
    assert await notifications.materialize() == 0
    await thread.send()(thread.command())
    assert await notifications.materialize() == 1
    provider = Transport(result=Outcome.UNKNOWN)
    usecase = DeliverNextStudentNotification(notifications, provider)
    assert await usecase()
    assert not await usecase()
    assert len(provider.calls) == 1


async def test_database_rejects_duplicate_source_recipient_and_rolls_back(
    identity_engine: AsyncEngine,
) -> None:
    thread = await chat(identity_engine)
    notifications = queue(identity_engine)
    await notifications.activate()
    await thread.send()(thread.command())
    assert await notifications.materialize() == 1
    async with notifications.sessions() as session:
        record = (await session.scalars(select(DeliveryRecord))).one()
        duplicate = DeliveryRecord(
            id=uuid4(),
            event_id=record.event_id,
            recipient_id=record.recipient_id,
            actor_id=record.actor_id,
            relationship_id=record.relationship_id,
            kind=record.kind,
            state=record.state,
            created_at=record.created_at,
            due_at=record.due_at,
            expires_at=record.expires_at,
            attempts=record.attempts,
            lease_token=record.lease_token,
            lease_until=record.lease_until,
        )
    with pytest.raises(IntegrityError):
        async with notifications.sessions.begin() as session:
            session.add(duplicate)
    async with notifications.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(DeliveryRecord)) == 1


async def test_real_block_after_enqueue_retires_without_provider(
    identity_engine: AsyncEngine,
) -> None:
    from studymate.application.discovery.profiles import ReadDiscoveryProfile
    from studymate.application.idempotency import IntentKey
    from studymate.application.safety.blocks import ChangeBlockCommand, ChangeOwnBlock
    from studymate.infrastructure.persistence.blocks import SqlBlockUnitOfWork
    from studymate.infrastructure.persistence.discovery_profiles import (
        SqlDiscoveryProfileUnitOfWork,
    )
    from tests.integration.requests.fixture import FINGERPRINTER, HASHER

    thread = await chat(identity_engine)
    notifications = queue(identity_engine)
    await notifications.activate()
    await thread.send()(thread.command())
    assert await notifications.materialize() == 1
    block = ChangeOwnBlock(SqlBlockUnitOfWork(thread.api.sessions), HASHER, FINGERPRINTER)
    profile = await ReadDiscoveryProfile(
        SqlDiscoveryProfileUnitOfWork(thread.api.sessions), HASHER
    )(thread.sender.credential, thread.recipient.id)
    await block(
        ChangeBlockCommand(
            thread.sender.credential,
            thread.recipient.id,
            True,
            0,
            IntentKey(str(uuid4())),
            profile.access_context.id,
        )
    )
    provider = Transport()
    assert await DeliverNextStudentNotification(notifications, provider)()
    assert provider.calls == []


async def test_changed_preference_still_permits_core_message_and_source_actor_is_rechecked(
    identity_engine: AsyncEngine,
) -> None:
    from studymate.application.idempotency import IntentKey
    from studymate.application.notification_preferences.preferences import (
        ChooseOwnNotificationPreference,
        ChoosePreferenceCommand,
    )
    from studymate.domain.notification_preferences.state import NotificationMode
    from studymate.infrastructure.notification_preferences.persistence import (
        SqlPreferenceUnitOfWork,
    )
    from studymate.infrastructure.persistence.product_events import (
        record_notification_preference_event,
    )
    from tests.integration.requests.fixture import FINGERPRINTER, HASHER
    from tests.integration.student_actor import actor

    thread = await chat(identity_engine)
    notifications = queue(identity_engine)
    await notifications.activate()
    choose = ChooseOwnNotificationPreference(
        SqlPreferenceUnitOfWork(notifications.sessions, record_notification_preference_event),
        HASHER,
        FINGERPRINTER,
    )
    await choose(
        ChoosePreferenceCommand(
            thread.recipient.credential, NotificationMode.ALL_UPDATES, 0, IntentKey(str(uuid4()))
        )
    )
    await thread.send()(thread.command())
    assert await notifications.materialize() == 1
    await choose(
        ChoosePreferenceCommand(
            thread.recipient.credential,
            NotificationMode.MESSAGES_AND_REQUESTS,
            1,
            IntentKey(str(uuid4())),
        )
    )
    provider = Transport()
    assert await DeliverNextStudentNotification(notifications, provider)()
    assert len(provider.calls) == 1  # Default mode is not an opt-out from messages.
    await thread.send()(thread.command())
    assert await notifications.materialize() == 1
    stranger = await actor(identity_engine)
    async with notifications.sessions.begin() as session:
        await session.execute(
            update(DeliveryRecord)
            .where(DeliveryRecord.state == State.PENDING.value)
            .values(recipient_id=stranger.id)
        )
    assert await DeliverNextStudentNotification(notifications, provider)()
    assert (
        len(provider.calls) == 1
    )  # Real immutable source, not stored queue target, owns recipient.


async def test_recipient_backpressure_is_bounded_and_unconsumed_source_survives(
    identity_engine: AsyncEngine,
) -> None:
    from studymate.infrastructure.student_notifications.queue import RECIPIENT_PENDING, SOURCE_BATCH

    thread = await chat(identity_engine)
    notifications = queue(identity_engine)
    await notifications.activate()
    for _ in range(RECIPIENT_PENDING + 1):
        await thread.send()(thread.command())
    assert await notifications.materialize() == SOURCE_BATCH
    assert await notifications.materialize() == SOURCE_BATCH
    assert await notifications.materialize() == 0
    async with notifications.sessions() as session:
        assert (
            await session.scalar(select(func.count()).select_from(DeliveryRecord))
            == RECIPIENT_PENDING
        )
    provider = Transport(result=Outcome.UNKNOWN)
    assert await DeliverNextStudentNotification(notifications, provider)()
    assert await notifications.materialize() == 1
    # Provider ambiguity never prevented an additional real core send.
    await thread.send()(thread.command())


async def test_source_transaction_rollback_never_leaks_a_notification(
    identity_engine: AsyncEngine,
) -> None:
    from tests.integration.test_message_commands import Recorder

    thread = await chat(identity_engine)
    notifications = queue(identity_engine)
    await notifications.activate()
    with pytest.raises(RuntimeError, match="Controlled message event failure"):
        await thread.send(Recorder(fail=True))(thread.command())
    assert await notifications.materialize() == 0
