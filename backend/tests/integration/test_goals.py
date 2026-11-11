import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.application.profiles.goals import (
    CompleteGoalCommand,
    CompleteOwnGoal,
    GoalVersionConflictError,
    ReadOwnGoal,
    SavedGoal,
    SaveGoalCommand,
    SaveOwnGoal,
    SubjectUnavailableError,
)
from studymate.domain.study_context import CanonicalSubjectRef, CustomSubjectRef, GoalContent
from studymate.infrastructure.persistence.catalogue import SqlSubjectReader
from studymate.infrastructure.persistence.catalogue_models import SubjectRecord
from studymate.infrastructure.persistence.goal_models import GoalRecord, GoalRevisionRecord
from studymate.infrastructure.persistence.goals import SqlGoalUnitOfWork
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
    SessionRecord,
)
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.catalogue_fixture import subject
from tests.integration.student_actor import Actor, actor

pytestmark = pytest.mark.integration


def services(engine: AsyncEngine) -> tuple[SaveOwnGoal, CompleteOwnGoal, ReadOwnGoal]:
    uow = SqlGoalUnitOfWork(async_sessionmaker(engine, expire_on_commit=False))
    hasher = Sha256SessionHasher()
    fingerprint = HmacIntentFingerprinter(bytes(range(32)))
    return (
        SaveOwnGoal(uow, hasher, fingerprint),
        CompleteOwnGoal(uow, hasher, fingerprint),
        ReadOwnGoal(uow, hasher),
    )


def command(owner: Actor, current: SavedGoal | None = None) -> SaveGoalCommand:
    return SaveGoalCommand(
        owner.credential,
        GoalContent(CustomSubjectRef("Synthetic subject")),
        current.goal.id if current is not None else None,
        current.goal.version if current is not None else 0,
        IntentKey(str(uuid4())),
    )


def completion(owner: Actor, current: SavedGoal) -> CompleteGoalCommand:
    return CompleteGoalCommand(
        owner.credential, current.goal.id, current.goal.version, IntentKey(str(uuid4()))
    )


async def test_goal_history_and_original_retry_survive_completion_and_replacement(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    save, complete, read = services(identity_engine)
    assert await read(owner.credential) is None
    submitted = command(owner)
    first = await save(submitted)
    edited = await save(
        replace(command(owner, first), content=replace(first.goal.content, topic="Private topic"))
    )
    close = completion(owner, edited)
    closed = await complete(close)
    assert closed.goal.completed_at is not None
    assert closed.goal.version == edited.goal.version + 1
    assert await read(owner.credential) is None
    replacement = await save(command(owner))
    assert replacement.goal.id != first.goal.id
    assert await save(submitted) == first
    assert await complete(close) == closed
    assert await read(owner.credential) == replacement
    with pytest.raises(GoalVersionConflictError) as stale:
        await complete(replace(close, intent_key=IntentKey(str(uuid4()))))
    assert stale.value.current_id == replacement.goal.id
    assert stale.value.current_version == replacement.goal.version
    async with async_sessionmaker(identity_engine)() as session:
        assert (
            await session.scalars(select(func.count()).select_from(GoalRevisionRecord))
        ).one() == closed.goal.version + replacement.goal.version


async def test_duplicate_goal_intent_serializes_and_different_payload_cannot_reuse_it(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    save, complete, _ = services(identity_engine)
    submitted = command(owner)
    first, duplicate = await asyncio.gather(save(submitted), save(submitted))
    assert first == duplicate
    with pytest.raises(IdempotencyConflictError):
        await save(replace(submitted, content=GoalContent(CustomSubjectRef("Other synthetic"))))
    with pytest.raises(IdempotencyConflictError):
        await complete(replace(completion(owner, first), intent_key=submitted.intent_key))
    closed, duplicate_closed = await asyncio.gather(
        complete(completion_command := completion(owner, first)), complete(completion_command)
    )
    assert closed == duplicate_closed


async def test_edit_completion_race_has_one_winner(identity_engine: AsyncEngine) -> None:
    owner = await actor(identity_engine)
    save, complete, read = services(identity_engine)
    original = await save(command(owner))

    async def edit() -> SavedGoal | GoalVersionConflictError:
        try:
            return await save(
                replace(
                    command(owner, original),
                    content=replace(original.goal.content, topic="Changed"),
                )
            )
        except GoalVersionConflictError as error:
            return error

    async def finish() -> SavedGoal | GoalVersionConflictError:
        try:
            return await complete(completion(owner, original))
        except GoalVersionConflictError as error:
            return error

    results = await asyncio.gather(edit(), finish())
    winners = [result for result in results if isinstance(result, SavedGoal)]
    assert len(winners) == 1
    assert sum(isinstance(result, GoalVersionConflictError) for result in results) == 1
    assert winners[0].goal.version == original.goal.version + 1
    current = await read(owner.credential)
    assert current == (winners[0] if winners[0].goal.completed_at is None else None)


async def test_unchanged_goal_has_no_revision_and_old_expectation_conflicts(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    save, complete, _ = services(identity_engine)
    initial = await save(command(owner))
    assert await save(command(owner, initial)) == initial
    with pytest.raises(GoalVersionConflictError):
        await save(command(owner))
    await complete(completion(owner, initial))
    with pytest.raises(GoalVersionConflictError) as empty:
        await complete(completion(owner, initial))
    assert empty.value.current_id is None
    assert empty.value.current_version == 0


async def test_canonical_choice_and_aliases_are_explicit_and_label_history_is_preserved(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    save, _, read = services(identity_engine)
    known = await subject(identity_engine)
    async with async_sessionmaker(identity_engine)() as session:
        assert await SqlSubjectReader(session).get(known.id) == known
        assert await SqlSubjectReader(session).get(uuid4()) is None
    canonical = await save(
        replace(command(owner), content=GoalContent(CanonicalSubjectRef(known.id)))
    )
    assert canonical.subject_label == known.name
    async with async_sessionmaker(identity_engine).begin() as session:
        await session.execute(
            update(SubjectRecord)
            .where(SubjectRecord.id == known.id)
            .values(
                name="Renamed synthetic",
                normalized_name="renamed synthetic",
                archived_at=func.clock_timestamp(),
            )
        )
    edited = await save(
        replace(
            command(owner, canonical),
            content=replace(canonical.goal.content, context="Private context"),
        )
    )
    assert edited.subject_label == known.name
    custom = await save(
        replace(command(owner, edited), content=GoalContent(CustomSubjectRef(known.name)))
    )
    assert custom.goal.content.canonical_subject_id is None
    assert await read(owner.credential) == custom
    with pytest.raises(SubjectUnavailableError):
        await save(
            replace(command(owner, custom), content=GoalContent(CanonicalSubjectRef(known.id)))
        )


@pytest.mark.parametrize("archived", [False, True])
async def test_unavailable_canonical_selection_does_not_save_goal(
    identity_engine: AsyncEngine, archived: bool
) -> None:
    owner = await actor(identity_engine)
    save, _, read = services(identity_engine)
    subject_id = (await subject(identity_engine, archived=True)).id if archived else uuid4()
    with pytest.raises(SubjectUnavailableError):
        await save(replace(command(owner), content=GoalContent(CanonicalSubjectRef(subject_id))))
    assert await read(owner.credential) is None


async def test_goal_ownership_and_intent_scope_are_account_bound(
    identity_engine: AsyncEngine,
) -> None:
    first, second = await actor(identity_engine), await actor(identity_engine)
    save, complete, read = services(identity_engine)
    submitted = command(first)
    own = await save(submitted)
    assert await read(second.credential) is None
    with pytest.raises(GoalVersionConflictError):
        await complete(replace(completion(first, own), credential=second.credential))
    other = await save(replace(submitted, credential=second.credential))
    assert other.goal.account_id == second.id
    assert other.goal.id != own.goal.id
    async with SqlGoalUnitOfWork(async_sessionmaker(identity_engine)).transaction() as transaction:
        assert await transaction.goal_version(second.id, own.goal.id, own.goal.version) is None


async def test_database_preserves_one_active_goal_and_referenced_history(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    save, _, _ = services(identity_engine)
    current = await save(command(owner))
    with pytest.raises(IntegrityError):
        async with async_sessionmaker(identity_engine).begin() as session:
            session.add(
                GoalRecord(
                    id=uuid4(), account_id=owner.id, current_version=1, created_at=datetime.now(UTC)
                )
            )
    with pytest.raises(IntegrityError):
        async with async_sessionmaker(identity_engine).begin() as session:
            await session.execute(
                delete(GoalRevisionRecord).where(GoalRevisionRecord.goal_id == current.goal.id)
            )


@pytest.mark.parametrize("restriction", ["unverified", "revoked", "banned", "deleted", "expired"])
async def test_goal_actions_require_live_verified_account(
    identity_engine: AsyncEngine, restriction: str
) -> None:
    owner = await actor(identity_engine)
    save, complete, read = services(identity_engine)
    original = await save(command(owner))
    async with async_sessionmaker(identity_engine).begin() as session:
        if restriction == "unverified":
            await session.execute(delete(InstitutionalBindingRecord))
        elif restriction == "revoked":
            await session.execute(
                update(InstitutionalBindingRecord).values(revoked_at=func.clock_timestamp())
            )
        elif restriction in {"banned", "deleted"}:
            await session.execute(
                update(AccountRecord).values({restriction + "_at": func.clock_timestamp()})
            )
        else:
            await session.execute(
                update(SessionRecord).values(
                    expires_at=func.clock_timestamp() - timedelta(seconds=1)
                )
            )
    denied = (
        UnauthenticatedError if restriction in {"deleted", "expired"} else StudentActionDeniedError
    )
    with pytest.raises(denied):
        await save(command(owner, original))
    with pytest.raises(denied):
        await complete(completion(owner, original))
    with pytest.raises(denied):
        await read(owner.credential)
    async with async_sessionmaker(identity_engine)() as session:
        assert (
            await session.scalars(select(func.count()).select_from(GoalRevisionRecord))
        ).one() == 1
