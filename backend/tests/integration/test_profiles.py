import asyncio
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import (
    StudentActionDeniedError,
    UnauthenticatedError,
)
from studymate.application.profiles.basics import (
    ProfileVersionConflictError,
    ReadOwnProfile,
    SaveOwnProfile,
    SaveProfileCommand,
    UnsupportedProfileLanguageError,
)
from studymate.domain.profiles import (
    DisplayName,
    LanguageCode,
    OnboardingTask,
    ProfileBasics,
    ProfileRevision,
)
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
    SessionRecord,
)
from studymate.infrastructure.persistence.profile_models import (
    ProfileLanguageRecord,
    ProfileRecord,
    ProfileRevisionRecord,
)
from studymate.infrastructure.persistence.profiles import SqlProfileUnitOfWork
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.student_actor import Actor, actor

pytestmark = pytest.mark.integration


def services(engine: AsyncEngine) -> tuple[SaveOwnProfile, ReadOwnProfile]:
    uow = SqlProfileUnitOfWork(async_sessionmaker(engine, expire_on_commit=False))
    hasher = Sha256SessionHasher()
    return SaveOwnProfile(uow, hasher, HmacIntentFingerprinter(bytes(range(32)))), ReadOwnProfile(
        uow, hasher
    )


def command(owner: Actor, *, version: int = 0) -> SaveProfileCommand:
    return SaveProfileCommand(
        owner.credential,
        ProfileBasics(
            DisplayName("Synthetic student"),
            about="Private profile history",
            languages=(LanguageCode("en"), LanguageCode("ms")),
        ),
        OnboardingTask.FIND_HELP,
        version,
        IntentKey(str(uuid4())),
    )


async def test_saved_steps_resume_and_old_intent_replays_original_revision(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    save, read = services(identity_engine)
    assert (await read(owner.credential)).profile is None
    first_command = command(owner)
    first = await save(first_command)
    assert first.account_id == owner.id
    assert (await read(owner.credential)).profile == first
    second = await save(
        replace(
            command(owner, version=first.version),
            basics=ProfileBasics(DisplayName("Changed synthetic name")),
            task=OnboardingTask.OFFER_HELP,
        )
    )
    assert second.version == first.version + 1
    assert await save(first_command) == first
    assert (await read(owner.credential)).profile == second
    async with async_sessionmaker(identity_engine)() as session:
        assert (
            await session.scalars(select(func.count()).select_from(ProfileRevisionRecord))
        ).one() == second.version
        old_languages = (
            await session.scalars(
                select(ProfileLanguageRecord.code)
                .where(
                    ProfileLanguageRecord.account_id == owner.id,
                    ProfileLanguageRecord.version == first.version,
                )
                .order_by(ProfileLanguageRecord.slot)
            )
        ).all()
        assert old_languages == ["en", "ms"]


async def test_duplicate_intent_is_atomic_and_changed_payload_conflicts(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    save, _ = services(identity_engine)
    submitted = command(owner)
    first, repeated = await asyncio.gather(save(submitted), save(submitted))
    assert first == repeated
    with pytest.raises(IdempotencyConflictError):
        await save(replace(submitted, basics=ProfileBasics(DisplayName("Different student"))))
    async with async_sessionmaker(identity_engine)() as session:
        assert (
            await session.scalars(select(func.count()).select_from(ProfileRevisionRecord))
        ).one() == 1


async def test_competing_edit_has_one_winner_and_no_lost_update(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    save, read = services(identity_engine)
    initial = await save(command(owner))

    async def submit(name: str) -> ProfileRevision | ProfileVersionConflictError:
        try:
            return await save(
                replace(
                    command(owner, version=initial.version), basics=ProfileBasics(DisplayName(name))
                )
            )
        except ProfileVersionConflictError as error:
            return error

    results = await asyncio.gather(submit("Synthetic first edit"), submit("Synthetic second edit"))
    winners = [result for result in results if isinstance(result, ProfileRevision)]
    conflicts = [result for result in results if isinstance(result, ProfileVersionConflictError)]
    assert len(winners) == 1
    assert len(conflicts) == 1
    assert conflicts[0].current_version == initial.version + 1
    assert (await read(owner.credential)).profile == winners[0]


async def test_unchanged_save_does_not_create_fictional_revision(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    save, _ = services(identity_engine)
    original = await save(command(owner))
    assert await save(command(owner, version=original.version)) == original
    with pytest.raises(ProfileVersionConflictError):
        await save(command(owner))


async def test_actor_scopes_current_profiles_and_intent_keys(identity_engine: AsyncEngine) -> None:
    first, second = await actor(identity_engine), await actor(identity_engine)
    save, read = services(identity_engine)
    submitted = command(first)
    own = await save(submitted)
    assert (await read(second.credential)).profile is None
    other = await save(replace(submitted, credential=second.credential))
    assert other.account_id == second.id
    assert other.account_id != own.account_id


@pytest.mark.parametrize("restriction", ["unverified", "revoked", "banned", "deleted", "expired"])
async def test_restricted_identity_cannot_read_or_save_student_profile(
    identity_engine: AsyncEngine, restriction: str
) -> None:
    owner = await actor(identity_engine, verified=restriction != "unverified")
    save, read = services(identity_engine)
    async with async_sessionmaker(identity_engine).begin() as session:
        if restriction == "revoked":
            await session.execute(
                update(InstitutionalBindingRecord).values(revoked_at=func.clock_timestamp())
            )
        elif restriction in {"banned", "deleted"}:
            await session.execute(
                update(AccountRecord).values({restriction + "_at": func.clock_timestamp()})
            )
        elif restriction == "expired":
            await session.execute(
                update(SessionRecord).values(
                    expires_at=func.clock_timestamp() - timedelta(seconds=1)
                )
            )
    error = (
        UnauthenticatedError if restriction in {"deleted", "expired"} else StudentActionDeniedError
    )
    with pytest.raises(error):
        await save(command(owner))
    with pytest.raises(error):
        await read(owner.credential)
    async with async_sessionmaker(identity_engine)() as session:
        assert (await session.scalars(select(func.count()).select_from(ProfileRecord))).one() == 0


async def test_language_slots_bound_even_direct_writes_and_history_cannot_be_deleted(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    save, _ = services(identity_engine)
    saved = await save(command(owner))
    with pytest.raises(IntegrityError):
        async with async_sessionmaker(identity_engine).begin() as session:
            session.add(
                ProfileLanguageRecord(account_id=owner.id, version=saved.version, slot=5, code="ar")
            )
    with pytest.raises(IntegrityError):
        async with async_sessionmaker(identity_engine).begin() as session:
            session.add(
                ProfileLanguageRecord(account_id=owner.id, version=saved.version, slot=2, code="en")
            )
    with pytest.raises(IntegrityError):
        async with async_sessionmaker(identity_engine).begin() as session:
            await session.execute(
                delete(ProfileRevisionRecord).where(
                    ProfileRevisionRecord.account_id == owner.id,
                    ProfileRevisionRecord.version == saved.version,
                )
            )


async def test_profile_language_reference_rejects_unknown_choices_without_saving(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    save, read = services(identity_engine)
    with pytest.raises(UnsupportedProfileLanguageError):
        await save(replace(command(owner), basics=ProfileBasics(languages=(LanguageCode("zz"),))))
    assert (await read(owner.credential)).profile is None
    good = await save(command(owner))
    with pytest.raises(IntegrityError):
        async with async_sessionmaker(identity_engine).begin() as session:
            session.add(
                ProfileLanguageRecord(account_id=owner.id, version=good.version, slot=2, code="zz")
            )
