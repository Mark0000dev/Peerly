import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.profiles.goals import SubjectUnavailableError
from studymate.application.profiles.help_subjects import (
    HelpVersionConflictError,
    ReadOwnHelpSubjects,
    SavedHelpSubjects,
    SaveHelpCommand,
    SaveOwnHelpSubjects,
)
from studymate.domain.study_context import HelpSubject, HelpSubjects
from studymate.infrastructure.persistence.catalogue_models import SubjectRecord
from studymate.infrastructure.persistence.help_models import HelpRevisionRecord, HelpSelectionRecord
from studymate.infrastructure.persistence.help_subjects import SqlHelpUnitOfWork
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.catalogue_fixture import subject
from tests.integration.student_actor import Actor, actor

pytestmark = pytest.mark.integration


def services(engine: AsyncEngine) -> tuple[SaveOwnHelpSubjects, ReadOwnHelpSubjects]:
    uow = SqlHelpUnitOfWork(async_sessionmaker(engine, expire_on_commit=False))
    hasher = Sha256SessionHasher()
    return SaveOwnHelpSubjects(
        uow, hasher, HmacIntentFingerprinter(bytes(range(32)))
    ), ReadOwnHelpSubjects(uow, hasher)


def command(
    owner: Actor, subjects: HelpSubjects | None = None, *, version: int = 0
) -> SaveHelpCommand:
    return SaveHelpCommand(
        owner.credential,
        subjects if subjects is not None else HelpSubjects(),
        version,
        IntentKey(str(uuid4())),
    )


async def test_help_revision_can_be_empty_and_original_intent_retains_private_history(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    save, read = services(identity_engine)
    assert await read(owner.credential) is None
    known = await subject(identity_engine)
    submitted = command(owner, HelpSubjects((HelpSubject(known.id, "Private original note"),)))
    first = await save(submitted)
    assert first.labels == (known.name,)
    cleared = await save(command(owner, version=first.revision.version))
    assert cleared.revision.subjects.values == ()
    assert await read(owner.credential) == cleared
    assert await save(submitted) == first
    assert await save(command(owner, version=cleared.revision.version)) == cleared
    with pytest.raises(HelpVersionConflictError):
        await save(command(owner))
    async with async_sessionmaker(identity_engine)() as session:
        assert (
            await session.scalars(select(func.count()).select_from(HelpRevisionRecord))
        ).one() == cleared.revision.version
        historical = (await session.scalars(select(HelpSelectionRecord))).one()
        assert historical.topic_note == "Private original note"


async def test_duplicate_help_intent_is_atomic_and_changed_payload_conflicts(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    save, _ = services(identity_engine)
    known = await subject(identity_engine)
    submitted = command(owner, HelpSubjects((HelpSubject(known.id),)))
    first, duplicate = await asyncio.gather(save(submitted), save(submitted))
    assert first == duplicate
    with pytest.raises(IdempotencyConflictError):
        await save(replace(submitted, subjects=HelpSubjects()))


async def test_competing_help_changes_have_one_winner(identity_engine: AsyncEngine) -> None:
    owner = await actor(identity_engine)
    save, read = services(identity_engine)
    known = await subject(identity_engine)
    initial = await save(command(owner, HelpSubjects((HelpSubject(known.id),))))

    async def edit(note: str) -> SavedHelpSubjects | HelpVersionConflictError:
        try:
            return await save(
                command(
                    owner,
                    HelpSubjects((HelpSubject(known.id, note),)),
                    version=initial.revision.version,
                )
            )
        except HelpVersionConflictError as error:
            return error

    results = await asyncio.gather(edit("First private note"), edit("Second private note"))
    winners = [value for value in results if isinstance(value, SavedHelpSubjects)]
    assert len(winners) == 1
    assert sum(isinstance(value, HelpVersionConflictError) for value in results) == 1
    assert await read(owner.credential) == winners[0]


async def test_archived_subject_can_remain_but_cannot_be_newly_selected(
    identity_engine: AsyncEngine,
) -> None:
    first, second = await actor(identity_engine), await actor(identity_engine)
    save, _ = services(identity_engine)
    known = await subject(identity_engine)
    selected = HelpSubjects((HelpSubject(known.id),))
    existing = await save(command(first, selected))
    async with async_sessionmaker(identity_engine).begin() as session:
        await session.execute(
            update(SubjectRecord)
            .where(SubjectRecord.id == known.id)
            .values(
                archived_at=func.clock_timestamp(),
                name="Renamed synthetic",
                normalized_name="renamed synthetic",
            )
        )
    edited = await save(
        command(
            first,
            HelpSubjects((HelpSubject(known.id, "Edited note"),)),
            version=existing.revision.version,
        )
    )
    assert edited.labels == (known.name,)
    with pytest.raises(SubjectUnavailableError):
        await save(command(second, selected))
    with pytest.raises(SubjectUnavailableError):
        await save(command(second, HelpSubjects((HelpSubject(uuid4()),))))


async def test_help_intents_and_histories_are_actor_owned(identity_engine: AsyncEngine) -> None:
    first, second = await actor(identity_engine), await actor(identity_engine)
    save, read = services(identity_engine)
    submitted = command(first)
    initial = await save(submitted)
    assert await read(second.credential) is None
    other = await save(replace(submitted, credential=second.credential))
    assert other.revision.account_id == second.id
    assert other.revision.account_id != initial.revision.account_id
    async with SqlHelpUnitOfWork(async_sessionmaker(identity_engine)).transaction() as transaction:
        assert await transaction.help_subjects(second.id, other.revision.version + 1) is None


async def test_help_selection_bounds_uniqueness_and_history_links_are_database_enforced(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    save, _ = services(identity_engine)
    known = await subject(identity_engine)
    initial = await save(command(owner, HelpSubjects((HelpSubject(known.id),))))
    for slot in (1, 5):
        with pytest.raises(IntegrityError):
            async with async_sessionmaker(identity_engine).begin() as session:
                session.add(
                    HelpSelectionRecord(
                        account_id=owner.id,
                        version=initial.revision.version,
                        slot=slot,
                        subject_id=known.id,
                        subject_label=known.name,
                    )
                )
    with pytest.raises(IntegrityError):
        async with async_sessionmaker(identity_engine).begin() as session:
            await session.execute(
                delete(HelpRevisionRecord).where(HelpRevisionRecord.account_id == owner.id)
            )


async def test_help_keeps_student_order_and_labels_after_sorted_locks(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    save, read = services(identity_engine)
    first = await subject(identity_engine, name="Synthetic first", aliases=())
    second = await subject(identity_engine, name="Synthetic second", aliases=())
    selected = HelpSubjects(
        (HelpSubject(second.id, "Second note"), HelpSubject(first.id, "First note"))
    )
    saved = await save(command(owner, selected))
    assert saved.revision.subjects == selected
    assert saved.labels == (second.name, first.name)
    assert await read(owner.credential) == saved
