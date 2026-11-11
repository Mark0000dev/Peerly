from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.identity.registration import (
    BeginRegistrationCommand,
    CompleteRegistrationCommand,
)
from studymate.application.profiles.onboarding import ReadOnboardingStatus
from studymate.application.profiles.visibility import ChangeOwnVisibility, ChangeVisibilityCommand
from studymate.infrastructure.persistence.onboarding import SqlProfileSetupUnitOfWork
from studymate.infrastructure.persistence.visibility import SqlVisibilityUnitOfWork
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.onboarding_fixture import ready_setup
from tests.integration.registration_fixture import documents
from tests.integration.student_actor import Actor, actor
from tests.integration.test_registration import registration


def services(engine: AsyncEngine) -> tuple[ChangeOwnVisibility, ReadOnboardingStatus]:
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    hasher = Sha256SessionHasher()
    return (
        ChangeOwnVisibility(
            SqlVisibilityUnitOfWork(sessions), hasher, HmacIntentFingerprinter(bytes(range(32)))
        ),
        ReadOnboardingStatus(SqlProfileSetupUnitOfWork(sessions), hasher),
    )


async def complete_existing_setup(engine: AsyncEngine, owner: Actor) -> None:
    begin, complete, _ = registration(engine)
    context = await begin(BeginRegistrationCommand(owner.credential, IntentKey(str(uuid4()))))
    await complete(
        CompleteRegistrationCommand(owner.credential, context.id, IntentKey(str(uuid4())))
    )


async def activated(engine: AsyncEngine) -> Actor:
    owner = await actor(engine)
    await ready_setup(engine, owner.credential)
    await documents(engine)
    await complete_existing_setup(engine, owner)
    return owner


def command(owner: Actor, *, hidden: bool = True, version: int = 1) -> ChangeVisibilityCommand:
    return ChangeVisibilityCommand(owner.credential, hidden, version, IntentKey(str(uuid4())))
