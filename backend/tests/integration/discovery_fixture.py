"""Genuine activated discovery actors with canonical learning/help declarations."""

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.profiles.goals import (
    ReadOwnGoal,
    SavedGoal,
    SaveGoalCommand,
    SaveOwnGoal,
)
from studymate.domain.catalogue import Subject
from studymate.domain.study_context import (
    CanonicalSubjectRef,
    GoalContent,
    HelpSubject,
    HelpSubjects,
)
from studymate.infrastructure.persistence.goals import SqlGoalUnitOfWork
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.catalogue_fixture import subject
from tests.integration.onboarding_fixture import ready_setup
from tests.integration.profile_lifecycle_fixture import complete_existing_setup
from tests.integration.safety_fixture import prepared
from tests.integration.student_actor import Actor, actor
from tests.integration.test_help_subjects import command as help_command
from tests.integration.test_help_subjects import services as help_services


@dataclass(frozen=True, slots=True)
class DiscoveryActors:
    viewer: Actor
    target: Actor
    goal: SavedGoal
    subject: Subject


async def discovery_actors(engine: AsyncEngine) -> DiscoveryActors:
    viewer, target, _ = await prepared(engine)
    known = await subject(engine)
    uow = SqlGoalUnitOfWork(async_sessionmaker(engine, expire_on_commit=False))
    hasher = Sha256SessionHasher()
    old = await ReadOwnGoal(uow, hasher)(viewer.credential)
    assert old is not None
    saved = await SaveOwnGoal(uow, hasher, HmacIntentFingerprinter(bytes(range(32))))(
        SaveGoalCommand(
            viewer.credential,
            GoalContent(CanonicalSubjectRef(known.id)),
            old.goal.id,
            old.goal.version,
            IntentKey(str(uuid4())),
        )
    )
    save_help, _ = help_services(engine)
    await save_help(help_command(target, HelpSubjects((HelpSubject(known.id),))))
    return DiscoveryActors(viewer, target, saved, known)


async def canonical_goal(
    engine: AsyncEngine,
    owner: Actor,
    subject_id: UUID,
    *,
    topic: str | None = None,
    shared: bool = False,
) -> SavedGoal:
    uow = SqlGoalUnitOfWork(async_sessionmaker(engine, expire_on_commit=False))
    hasher = Sha256SessionHasher()
    old = await ReadOwnGoal(uow, hasher)(owner.credential)
    assert old is not None
    return await SaveOwnGoal(uow, hasher, HmacIntentFingerprinter(bytes(range(32))))(
        SaveGoalCommand(
            owner.credential,
            GoalContent(CanonicalSubjectRef(subject_id), topic=topic, shared_learning=shared),
            old.goal.id,
            old.goal.version,
            IntentKey(str(uuid4())),
        )
    )


async def additional_helper(
    engine: AsyncEngine, subject_id: UUID, *, topic: str | None = None
) -> Actor:
    owner = await actor(engine)
    await ready_setup(engine, owner.credential)
    await complete_existing_setup(engine, owner)
    save, _ = help_services(engine)
    await save(help_command(owner, HelpSubjects((HelpSubject(subject_id, topic),))))
    return owner
