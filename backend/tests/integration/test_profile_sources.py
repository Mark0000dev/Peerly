from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import studymate.infrastructure.persistence.profile_sources as source_module
from studymate.application.idempotency import IntentKey
from studymate.application.safety.blocks import ChangeBlockCommand, ChangeOwnBlock
from studymate.domain.profiles import LanguageCode
from studymate.domain.study_context import HelpSubject, HelpSubjects
from studymate.infrastructure.persistence.blocks import SqlBlockUnitOfWork
from studymate.infrastructure.persistence.discovery_profiles import SqlDiscoveryProfileReader
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.profile_models import ProfileRevisionRecord
from studymate.infrastructure.persistence.profile_sources import (
    MAX_PROFILE_SOURCE_BATCH,
    read_blocked_peers,
    read_profile_languages,
    read_profile_sources,
)
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.discovery_fixture import discovery_actors
from tests.integration.profile_lifecycle_fixture import command as visibility_command
from tests.integration.profile_lifecycle_fixture import services as visibility_services
from tests.integration.safety_fixture import prepared
from tests.integration.student_actor import actor
from tests.integration.test_help_subjects import command as help_command
from tests.integration.test_help_subjects import services as help_services

pytestmark = pytest.mark.integration


async def test_bulk_source_equals_current_single_sources_including_incomplete_accounts(
    identity_engine: AsyncEngine,
) -> None:
    actors = await discovery_actors(identity_engine)
    incomplete = await actor(identity_engine, verified=False)
    ids = (actors.viewer.id, actors.target.id, incomplete.id, uuid4())
    async with async_sessionmaker(identity_engine, expire_on_commit=False)() as session:
        result = await read_profile_sources(session, ids)
        single = SqlDiscoveryProfileReader(session)
        for account_id in ids:
            assert result.get(account_id) == await single.profile_source(account_id)
    assert result[actors.target.id].can_make_new_contacts
    assert not result[incomplete.id].can_make_new_contacts
    assert result[incomplete.id].setup.profile is None
    assert result[incomplete.id].membership is None


async def test_bulk_projection_preserves_deleted_banned_sources_without_granting_contact(
    identity_engine: AsyncEngine,
) -> None:
    actors = await discovery_actors(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == actors.viewer.id)
            .values(deleted_at=datetime.now(UTC))
        )
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == actors.target.id)
            .values(banned_at=datetime.now(UTC))
        )
    async with sessions() as session:
        result = await read_profile_sources(session, (actors.viewer.id, actors.target.id))
    assert result[actors.viewer.id].deleted
    assert result[actors.target.id].banned
    assert all(not value.can_make_new_contacts for value in result.values())
    assert all(value.setup.profile is not None for value in result.values())


async def test_bulk_sources_have_constant_select_count_and_empty_scope_performs_no_io(
    identity_engine: AsyncEngine,
) -> None:
    owners = tuple([await actor(identity_engine) for _ in range(21)])
    counts: list[int] = []
    statements: list[str] = []

    def observe(*arguments: object) -> None:
        statement = arguments[2]
        if isinstance(statement, str) and statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(identity_engine.sync_engine, "before_cursor_execute", observe)
    try:
        for size in (1, 21):
            statements.clear()
            async with async_sessionmaker(identity_engine)() as session:
                result = await read_profile_sources(
                    session, tuple(owner.id for owner in owners[:size])
                )
                assert len(result) == size
            counts.append(len(statements))
        expected_select_count = 5
        assert counts[0] == counts[1] == expected_select_count
        statements.clear()
        async with async_sessionmaker(identity_engine)() as session:
            assert await read_profile_sources(session, ()) == {}
            assert await read_blocked_peers(session, owners[0].id, ()) == frozenset()
            with pytest.raises(ValueError, match="bounded"):
                await read_profile_sources(
                    session, tuple(uuid4() for _ in range(MAX_PROFILE_SOURCE_BATCH + 1))
                )
        assert not statements
    finally:
        event.remove(identity_engine.sync_engine, "before_cursor_execute", observe)


@pytest.mark.parametrize("reverse", [False, True])
async def test_bulk_blocks_project_either_direction_and_only_requested_peers(
    identity_engine: AsyncEngine,
    reverse: bool,
) -> None:
    viewer, target, context = await prepared(identity_engine)
    # The actual retained disclosure authorises the viewer's block command.
    services = ChangeOwnBlock(
        SqlBlockUnitOfWork(async_sessionmaker(identity_engine, expire_on_commit=False)),
        Sha256SessionHasher(),
        HmacIntentFingerprinter(bytes(range(32))),
    )
    await services(
        ChangeBlockCommand(
            viewer.credential, target.id, True, 0, IntentKey(str(uuid4())), context.id
        )
    )
    owner, peer = (target, viewer) if reverse else (viewer, target)
    async with async_sessionmaker(identity_engine)() as session:
        assert await read_blocked_peers(session, owner.id, (peer.id, uuid4())) == frozenset(
            (peer.id,)
        )
        assert not await read_blocked_peers(session, owner.id, (uuid4(),))


async def test_batch_source_keeps_the_help_version_captured_before_concurrent_hide_and_edit(
    identity_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = await discovery_actors(identity_engine)
    original = read_profile_languages

    async def edit_after_source_row(
        session: AsyncSession, profiles: tuple[ProfileRevisionRecord, ...]
    ) -> dict[UUID, tuple[LanguageCode, ...]]:
        visibility, _ = visibility_services(identity_engine)
        await visibility(visibility_command(setup.target))
        save, _ = help_services(identity_engine)
        await save(
            help_command(
                setup.target,
                HelpSubjects((HelpSubject(setup.subject.id, "Synthetic private post-hide edit"),)),
                version=1,
            )
        )
        return await original(session, profiles)

    monkeypatch.setattr(source_module, "read_profile_languages", edit_after_source_row)
    async with async_sessionmaker(identity_engine, expire_on_commit=False)() as session:
        sources = await read_profile_sources(session, (setup.viewer.id, setup.target.id))
        help_subjects = sources[setup.target.id].setup.help_subjects
        assert help_subjects is not None
        assert help_subjects.revision.version == 1
        assert help_subjects.revision.subjects.values[0].topic_note is None
