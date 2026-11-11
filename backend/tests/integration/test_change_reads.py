import asyncio
from time import perf_counter

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.changes.publication import PublishChanges
from studymate.application.changes.reads import ReadChanges
from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.domain.changes import MAX_DELIVERY_SEQUENCE, ChangeResource
from studymate.infrastructure.changes.models import (
    ChangeHeadRecord,
    PublishedChangeRecord,
)
from studymate.infrastructure.changes.publication import SqlChangePublicationUnitOfWork
from studymate.infrastructure.changes.reads import SqlChangeReadUnitOfWork
from studymate.infrastructure.persistence.discovery_freshness_models import DiscoveryExposureRecord
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord
from studymate.infrastructure.persistence.message_read_models import ConversationReadPositionRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from tests.integration.change_fixture import message_events, stage
from tests.integration.requests.fixture import HASHER
from tests.integration.test_message_commands import chat

pytestmark = pytest.mark.integration
MINIMUM_LOCK_WAIT_SECONDS = 1.8


async def test_initial_reset_resume_and_future_reset_keep_owned_scope_without_implicit_activity(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    reader = ReadChanges(SqlChangeReadUnitOfWork(owned.api.sessions), HASHER)
    initial = await reader(owned.recipient.credential, None)
    assert initial.reset_required
    assert initial.after_sequence == 0
    assert not initial.changes
    async with owned.api.sessions() as session:
        assert not tuple(await session.scalars(select(ChangeHeadRecord)))
    await owned.send()(owned.command())
    await stage(owned, await message_events(owned))
    await PublishChanges(SqlChangePublicationUnitOfWork(owned.api.sessions))()
    async with owned.api.sessions() as session:
        before = {
            row.account_id: row.last_activity_at
            for row in await session.scalars(select(DiscoveryExposureRecord))
        }
        canonical = frozenset(await session.scalars(select(ProductEventRecord.id)))
    reset = await reader(owned.recipient.credential, None)
    assert reset.reset_required
    assert reset.after_sequence >= 1
    assert not reset.changes
    caught = await reader(owned.recipient.credential, 0)
    assert not caught.reset_required
    assert caught.after_sequence == reset.after_sequence
    assert len(caught.changes) == reset.after_sequence
    assert all(item.hint.recipient_id == owned.recipient.id for item in caught.changes)
    source = (await message_events(owned))[0]
    message_hints = tuple(
        item.hint for item in caught.changes if item.hint.canonical_event_id == source.id
    )
    assert len(message_hints) == 1
    assert message_hints[0].resource_type == ChangeResource.CONVERSATION
    assert message_hints[0].resource_id == owned.conversation_id
    idle = await reader(owned.recipient.credential, caught.after_sequence)
    assert not idle.changes
    assert idle.after_sequence == caught.after_sequence
    future = await reader(owned.recipient.credential, MAX_DELIVERY_SEQUENCE)
    assert future.reset_required
    assert future.after_sequence == reset.after_sequence
    async with owned.api.sessions() as session:
        assert {
            row.account_id: row.last_activity_at
            for row in await session.scalars(select(DiscoveryExposureRecord))
        } == before
        assert frozenset(await session.scalars(select(ProductEventRecord.id))) == canonical
        assert not tuple(await session.scalars(select(ConversationReadPositionRecord)))


@pytest.mark.parametrize("state", ["banned", "deleted", "revoked"])
async def test_reconnect_rechecks_live_authority_after_a_previous_successful_poll(
    identity_engine: AsyncEngine,
    state: str,
) -> None:
    owned = await chat(identity_engine)
    reader = ReadChanges(SqlChangeReadUnitOfWork(owned.api.sessions), HASHER)
    assert (await reader(owned.sender.credential, None)).reset_required
    async with owned.api.sessions.begin() as session:
        if state == "revoked":
            await session.execute(
                update(SessionRecord)
                .where(SessionRecord.account_id == owned.sender.id)
                .values(revoked_at=func.clock_timestamp())
            )
        else:
            await session.execute(
                update(AccountRecord)
                .where(AccountRecord.id == owned.sender.id)
                .values(
                    {
                        AccountRecord.banned_at
                        if state == "banned"
                        else AccountRecord.deleted_at: func.clock_timestamp()
                    }
                )
            )
    with pytest.raises((UnauthenticatedError, StudentActionDeniedError)):
        await reader(owned.sender.credential, 0)


async def test_source_window_cannot_be_read_with_another_recipient_argument(
    identity_engine: AsyncEngine,
) -> None:
    from studymate.application.identity.sessions import require_verified_student

    owned = await chat(identity_engine)
    uow = SqlChangeReadUnitOfWork(owned.api.sessions)
    async with uow.transaction() as transaction:
        await require_verified_student(transaction, await HASHER.digest(owned.sender.credential))
        with pytest.raises(RuntimeError, match="actual authenticated recipient"):
            await transaction.change_window(owned.recipient.id, 0)
    async with owned.api.sessions() as session:
        assert not tuple(await session.scalars(select(PublishedChangeRecord)))


async def test_change_read_total_deadline_covers_session_lock_wait_without_holding_a_connection(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    reader = ReadChanges(SqlChangeReadUnitOfWork(owned.api.sessions), HASHER)
    async with owned.api.sessions.begin() as blocker:
        await blocker.scalar(
            select(SessionRecord)
            .where(SessionRecord.account_id == owned.sender.id)
            .with_for_update()
        )
        started = perf_counter()
        async with asyncio.timeout(3):
            with pytest.raises(StorageUnavailableError):
                await reader(owned.sender.credential, None)
        assert perf_counter() - started >= MINIMUM_LOCK_WAIT_SECONDS
    assert (await reader(owned.sender.credential, None)).reset_required
