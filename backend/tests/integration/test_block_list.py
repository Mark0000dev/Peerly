from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import event, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.profiles.basics import SaveOwnProfile, SaveProfileCommand
from studymate.application.safety.block_list import (
    BLOCKS_PAGE_SIZE,
    InvalidBlockCursorError,
    ReadOwnBlocks,
)
from studymate.application.safety.blocks import ChangeBlockCommand, ChangeOwnBlock
from studymate.domain.profiles import DisplayName, OnboardingTask, ProfileBasics
from studymate.domain.relationships import AccountPair, BlockRevision
from studymate.infrastructure.persistence.block_list import SqlOwnBlocksUnitOfWork
from studymate.infrastructure.persistence.blocks import SqlBlockTransaction, SqlBlockUnitOfWork
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.profiles import SqlProfileUnitOfWork
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.profile_lifecycle_fixture import command as visibility_command
from tests.integration.profile_lifecycle_fixture import services as visibility_services
from tests.integration.safety_fixture import prepared

pytestmark = pytest.mark.integration


def reader(engine: AsyncEngine) -> ReadOwnBlocks:
    return ReadOwnBlocks(
        SqlOwnBlocksUnitOfWork(async_sessionmaker(engine, expire_on_commit=False)),
        Sha256SessionHasher(),
    )


def writer(engine: AsyncEngine) -> ChangeOwnBlock:
    return ChangeOwnBlock(
        SqlBlockUnitOfWork(async_sessionmaker(engine, expire_on_commit=False)),
        Sha256SessionHasher(),
        HmacIntentFingerprinter(bytes(range(32))),
    )


async def test_own_block_management_uses_known_disclosure_not_hidden_name_updates(
    identity_engine: AsyncEngine,
) -> None:
    viewer, target, context = await prepared(identity_engine)
    change = writer(identity_engine)
    original = ChangeBlockCommand(
        viewer.credential, target.id, True, 0, IntentKey(str(uuid4())), context.id
    )
    await change(original)
    listing = reader(identity_engine)
    first = await listing(viewer.credential)
    assert len(first.people) == 1
    old_name = first.people[0].display_name
    assert old_name is not None
    await SaveOwnProfile(
        SqlProfileUnitOfWork(async_sessionmaker(identity_engine, expire_on_commit=False)),
        Sha256SessionHasher(),
        HmacIntentFingerprinter(bytes(range(32))),
    )(
        SaveProfileCommand(
            target.credential,
            ProfileBasics(DisplayName("Changed after blocking")),
            OnboardingTask.FIND_HELP,
            1,
            IntentKey(str(uuid4())),
        )
    )
    visibility, _ = visibility_services(identity_engine)
    await visibility(visibility_command(viewer))
    after = await listing(viewer.credential)
    assert after.people[0].display_name == old_name
    assert after.people[0].block.target_id == target.id
    await change(
        replace(
            original,
            blocked=False,
            expected_version=1,
            intent_key=IntentKey(str(uuid4())),
            context_id=None,
        )
    )
    assert not (await listing(viewer.credential)).people


async def test_deleted_target_is_masked_but_own_block_remains_manageable(
    identity_engine: AsyncEngine,
) -> None:
    viewer, target, context = await prepared(identity_engine)
    change = writer(identity_engine)
    original = ChangeBlockCommand(
        viewer.credential, target.id, True, 0, IntentKey(str(uuid4())), context.id
    )
    await change(original)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        transaction = SqlBlockTransaction(session, target.id)
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == target.id)
            .values(deleted_at=await transaction.now())
        )
    result = await reader(identity_engine)(viewer.credential)
    assert len(result.people) == 1
    assert result.people[0].deleted
    assert result.people[0].display_name is None
    await change(
        replace(
            original,
            blocked=False,
            expected_version=1,
            intent_key=IntentKey(str(uuid4())),
            context_id=None,
        )
    )
    assert not (await reader(identity_engine)(viewer.credential)).people


async def test_owner_keyset_pages_are_complete_scoped_and_have_constant_query_count(
    identity_engine: AsyncEngine,
) -> None:
    viewer, other, _ = await prepared(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    targets = tuple(uuid4() for _ in range(BLOCKS_PAGE_SIZE + 2))
    # Synthetic retained legacy blocks deliberately have no invented disclosure/name.
    async with sessions.begin() as session:
        transaction = SqlBlockTransaction(session, other.id)
        now = await transaction.now()
        session.add_all(AccountRecord(id=target_id, created_at=now) for target_id in targets)
        await session.flush()
        for target_id in targets:
            await transaction.save_block(
                BlockRevision(
                    uuid4(), AccountPair.between(viewer.id, target_id), viewer.id, 1, True, now
                )
            )
        await transaction.save_block(
            BlockRevision(uuid4(), AccountPair.between(viewer.id, other.id), other.id, 1, True, now)
        )
    selects: list[str] = []

    def count(*arguments: object) -> None:
        statement = arguments[2]
        if isinstance(statement, str) and statement.startswith("SELECT"):
            selects.append(statement)

    event.listen(identity_engine.sync_engine, "before_cursor_execute", count)
    try:
        service = reader(identity_engine)
        first = await service(viewer.credential)
        first_queries = len(selects)
        selects.clear()
        assert first.next_cursor is not None
        second = await service(viewer.credential, first.next_cursor)
        assert len(selects) == first_queries
    finally:
        event.remove(identity_engine.sync_engine, "before_cursor_execute", count)
    people = first.people + second.people
    assert tuple(person.block.target_id for person in people) == tuple(sorted(targets))
    assert second.next_cursor is None
    assert all(person.actor_id == viewer.id for person in people)
    assert all(person.display_name is None for person in people)
    with pytest.raises(InvalidBlockCursorError):
        await service(other.credential, first.next_cursor)
