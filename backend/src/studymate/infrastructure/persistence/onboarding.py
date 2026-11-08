from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.profiles.onboarding import ProfileSetupSnapshot
from studymate.domain.onboarding import OnboardingActivation, ProfileLifecycle
from studymate.infrastructure.persistence.discovery_exposure import (
    initialize_discovery_exposure,
    read_discovery_exposure,
    read_freshness_policy,
)
from studymate.infrastructure.persistence.goals import SqlGoalTransaction
from studymate.infrastructure.persistence.help_subjects import SqlHelpTransaction
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.media_uploads import SqlMediaTransaction
from studymate.infrastructure.persistence.onboarding_models import (
    ProfileActivationRecord,
    VisibilityRevisionRecord,
)
from studymate.infrastructure.persistence.product_events import record_activation_event
from studymate.infrastructure.persistence.profiles import SqlProfileTransaction
from studymate.infrastructure.persistence.transactions import open_transaction


async def read_lifecycle(session: AsyncSession, account_id: UUID) -> ProfileLifecycle | None:
    record = (
        await session.scalars(
            select(VisibilityRevisionRecord)
            .join(
                ProfileActivationRecord,
                (ProfileActivationRecord.account_id == VisibilityRevisionRecord.account_id)
                & (ProfileActivationRecord.visibility_version == VisibilityRevisionRecord.version),
            )
            .where(VisibilityRevisionRecord.account_id == account_id)
        )
    ).one_or_none()
    if record is None:
        return None
    return ProfileLifecycle(
        account_id, record.completed_at, record.version, record.hidden_at, record.changed_at
    )


async def read_setup_snapshot(session: AsyncSession, account_id: UUID) -> ProfileSetupSnapshot:
    return ProfileSetupSnapshot(
        account_id,
        await SqlProfileTransaction(session).profile(account_id),
        await SqlMediaTransaction(session).current_photo(account_id),
        await SqlGoalTransaction(session).active_goal(account_id),
        await SqlHelpTransaction(session).help_subjects(account_id),
        await read_lifecycle(session, account_id),
        await read_discovery_exposure(session, account_id),
        await read_freshness_policy(session, await SqlIdentityTransaction(session).now()),
    )


async def record_activation(session: AsyncSession, activation: OnboardingActivation) -> None:
    account_id = activation.profile.account_id
    session.add(
        ProfileActivationRecord(
            account_id=account_id,
            registration_id=activation.registration.id,
            profile_version=activation.profile.version,
            photo_version=activation.photo.version,
            goal_id=activation.goal.id if activation.goal is not None else None,
            goal_version=activation.goal.version if activation.goal is not None else None,
            help_version=activation.help_revision.version
            if activation.help_revision is not None
            else None,
            completed_at=activation.completed_at,
            visibility_version=1,
        )
    )
    await session.flush()
    session.add(
        VisibilityRevisionRecord(
            account_id=account_id,
            version=1,
            completed_at=activation.completed_at,
            hidden_at=None,
            changed_at=activation.completed_at,
        )
    )
    await session.flush()

    await initialize_discovery_exposure(session, account_id, activation.completed_at)
    await record_activation_event(session, activation)


@dataclass(frozen=True, slots=True)
class SqlProfileSetupTransaction(SqlIdentityTransaction):
    async def setup_snapshot(self, account_id: UUID) -> ProfileSetupSnapshot:
        return await read_setup_snapshot(self.session, account_id)


@dataclass(frozen=True, slots=True)
class SqlProfileSetupUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlProfileSetupTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlProfileSetupTransaction(session)
