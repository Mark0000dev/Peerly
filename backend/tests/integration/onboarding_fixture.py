"""Explicit real saved steps; never an implicit ready-account default."""

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import SessionCredential
from studymate.application.media.worker import PhotoProcessingStep
from studymate.application.profiles.basics import SaveOwnProfile, SaveProfileCommand
from studymate.application.profiles.goals import SaveGoalCommand, SaveOwnGoal
from studymate.domain.profiles import DisplayName, OnboardingTask, ProfileBasics
from studymate.domain.study_context import CustomSubjectRef, GoalContent
from studymate.infrastructure.media.images import BoundedImageProcessor
from studymate.infrastructure.persistence.goals import SqlGoalUnitOfWork
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityUnitOfWork
from studymate.infrastructure.persistence.profiles import SqlProfileUnitOfWork
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.image_fixture import encoded
from tests.integration.media_fixture import Storage, queued, worker
from tests.integration.student_actor import Actor


async def ready_setup(engine: AsyncEngine, credential: SessionCredential) -> Actor:
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    hasher = Sha256SessionHasher()
    async with SqlIdentityUnitOfWork(sessions).transaction() as transaction:
        identity = await transaction.lock_identity(await hasher.digest(credential))
        assert identity is not None
        owner = Actor(identity.session.account_id, credential)
    fingerprint = HmacIntentFingerprinter(bytes(range(32)))
    await SaveOwnProfile(SqlProfileUnitOfWork(sessions), hasher, fingerprint)(
        SaveProfileCommand(
            credential,
            ProfileBasics(DisplayName("Synthetic student")),
            OnboardingTask.FIND_HELP,
            0,
            IntentKey(str(uuid4())),
        )
    )
    await SaveOwnGoal(SqlGoalUnitOfWork(sessions), hasher, fingerprint)(
        SaveGoalCommand(
            credential,
            GoalContent(CustomSubjectRef("Synthetic custom topic")),
            None,
            0,
            IntentKey(str(uuid4())),
        )
    )
    source = encoded()
    await queued(engine, owner, source)
    processor = BoundedImageProcessor()
    try:
        assert await worker(engine, Storage(source), processor)() == PhotoProcessingStep.READY
    finally:
        await processor.close()
    return owner
