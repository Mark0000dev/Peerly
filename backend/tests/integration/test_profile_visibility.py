import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.application.profiles.basics import (
    ProfileNameRequiredError,
    SaveOwnProfile,
    SaveProfileCommand,
)
from studymate.application.profiles.goals import CompleteGoalCommand, CompleteOwnGoal
from studymate.application.profiles.visibility import (
    ProfileRestoreIncompleteError,
    VisibilityVersionConflictError,
)
from studymate.domain.profiles import OnboardingTask, ProfileBasics
from studymate.infrastructure.persistence.goals import SqlGoalUnitOfWork
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.onboarding import SqlProfileSetupUnitOfWork
from studymate.infrastructure.persistence.onboarding_models import VisibilityRevisionRecord
from studymate.infrastructure.persistence.profiles import SqlProfileUnitOfWork
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.profile_lifecycle_fixture import activated, command, services
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration


async def test_visibility_keeps_original_intent_revisions_and_activation_history(
    identity_engine: AsyncEngine,
) -> None:
    owner = await activated(identity_engine)
    change, status = services(identity_engine)
    initial = await status(owner.credential)
    assert initial.registered
    assert initial.setup_complete
    assert initial.capabilities.can_discover
    hidden_command = command(owner)
    first, replay = await asyncio.gather(change(hidden_command), change(hidden_command))
    assert first == replay
    hidden = await status(owner.credential)
    assert hidden.capabilities.can_access_existing_chats
    assert not hidden.capabilities.can_make_new_contacts
    assert hidden.capabilities.can_restore_profile
    assert await change(command(owner, version=first.visibility_version)) == first
    restored = await change(command(owner, hidden=False, version=first.visibility_version))
    assert not restored.hidden
    assert restored.completed_at == first.completed_at
    assert await change(hidden_command) == first
    assert (await status(owner.credential)).lifecycle == restored
    with pytest.raises(IdempotencyConflictError):
        await change(replace(hidden_command, hidden=False))
    with pytest.raises(VisibilityVersionConflictError) as stale:
        await change(command(owner))
    assert stale.value.current_version == restored.visibility_version
    async with async_sessionmaker(identity_engine)() as session:
        assert (
            await session.scalars(select(func.count()).select_from(VisibilityRevisionRecord))
        ).one() == restored.visibility_version


async def test_hidden_context_completion_preserves_chats_but_blocks_restore(
    identity_engine: AsyncEngine,
) -> None:
    owner = await activated(identity_engine)
    change, status = services(identity_engine)
    hidden = await change(command(owner))
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with SqlProfileSetupUnitOfWork(sessions).transaction() as transaction:
        snapshot = await transaction.setup_snapshot(owner.id)
    assert snapshot.goal is not None
    goal = snapshot.goal.goal
    await CompleteOwnGoal(
        SqlGoalUnitOfWork(sessions),
        Sha256SessionHasher(),
        HmacIntentFingerprinter(bytes(range(32))),
    )(CompleteGoalCommand(owner.credential, goal.id, goal.version, IntentKey(str(uuid4()))))
    current = await status(owner.credential)
    assert current.setup_complete
    assert current.capabilities.can_access_existing_chats
    with pytest.raises(ProfileRestoreIncompleteError) as missing:
        await change(command(owner, hidden=False, version=hidden.visibility_version))
    assert tuple(item.value for item in missing.value.requirements) == ("study_context",)
    assert (await status(owner.credential)).lifecycle == hidden


@pytest.mark.parametrize("state", ["unverified", "draft", "banned", "deleted"])
async def test_visibility_never_bypasses_identity_or_initial_completion(
    identity_engine: AsyncEngine, state: str
) -> None:
    owner = (
        await activated(identity_engine)
        if state in {"banned", "deleted"}
        else await actor(identity_engine, verified=state != "unverified")
    )
    if state in {"banned", "deleted"}:
        async with async_sessionmaker(identity_engine).begin() as session:
            column = AccountRecord.banned_at if state == "banned" else AccountRecord.deleted_at
            await session.execute(
                update(AccountRecord)
                .where(AccountRecord.id == owner.id)
                .values({column: func.clock_timestamp()})
            )
    change, _ = services(identity_engine)
    with pytest.raises(UnauthenticatedError if state == "deleted" else StudentActionDeniedError):
        await change(command(owner))


async def test_completed_profile_cannot_clear_its_name(identity_engine: AsyncEngine) -> None:
    owner = await activated(identity_engine)
    save = SaveOwnProfile(
        SqlProfileUnitOfWork(async_sessionmaker(identity_engine, expire_on_commit=False)),
        Sha256SessionHasher(),
        HmacIntentFingerprinter(bytes(range(32))),
    )
    with pytest.raises(ProfileNameRequiredError):
        await save(
            SaveProfileCommand(
                owner.credential,
                ProfileBasics(),
                OnboardingTask.FIND_HELP,
                1,
                IntentKey(str(uuid4())),
            )
        )


async def test_distinct_competing_visibility_intents_have_one_revision_winner(
    identity_engine: AsyncEngine,
) -> None:
    owner = await activated(identity_engine)
    change, status = services(identity_engine)

    async def submit() -> bool:
        try:
            await change(command(owner))
        except VisibilityVersionConflictError:
            return False
        return True

    assert sorted(await asyncio.gather(submit(), submit())) == [False, True]
    current = await status(owner.credential)
    assert current.lifecycle is not None
    assert current.lifecycle.hidden
    assert current.lifecycle.visibility_version == 1 + 1


@pytest.mark.parametrize("state", ["banned", "deleted"])
async def test_account_lock_orders_visibility_against_lifecycle_change(
    identity_engine: AsyncEngine, state: str
) -> None:
    owner = await activated(identity_engine)
    change, _ = services(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        await session.execute(
            select(AccountRecord).where(AccountRecord.id == owner.id).with_for_update()
        )
        pending = asyncio.create_task(change(command(owner)))
        column = AccountRecord.banned_at if state == "banned" else AccountRecord.deleted_at
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == owner.id)
            .values({column: func.clock_timestamp()})
        )
    with pytest.raises(UnauthenticatedError if state == "deleted" else StudentActionDeniedError):
        await pending
    async with sessions() as session:
        assert (
            await session.scalars(select(func.count()).select_from(VisibilityRevisionRecord))
        ).one() == 1
