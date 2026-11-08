from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from studymate.application.identity.sessions import (
    IdentityReader,
    SessionCredential,
    SessionHasher,
    require_verified_student,
)
from studymate.application.profiles.goals import SavedGoal
from studymate.application.profiles.help_subjects import SavedHelpSubjects
from studymate.domain.discovery_freshness import DiscoveryExposure, DiscoveryFreshnessPolicy
from studymate.domain.media import PhotoRevision
from studymate.domain.onboarding import ProfileLifecycle
from studymate.domain.profile_readiness import (
    ProfileCapabilities,
    RestoreRequirement,
    StudentProfileState,
    profile_capabilities,
)
from studymate.domain.profiles import OnboardingTask, ProfileBasics, ProfileRevision
from studymate.domain.study_context import HelpSubjects


@dataclass(frozen=True, slots=True)
class ProfileSetupSnapshot:
    account_id: UUID
    profile: ProfileRevision | None = field(repr=False)
    photo: PhotoRevision | None
    goal: SavedGoal | None = field(repr=False)
    help_subjects: SavedHelpSubjects | None = field(repr=False)
    lifecycle: ProfileLifecycle | None
    exposure: DiscoveryExposure | None = None
    freshness_policy: DiscoveryFreshnessPolicy = field(default_factory=DiscoveryFreshnessPolicy)

    def state(self) -> StudentProfileState:
        return StudentProfileState(
            account_id=self.account_id,
            basics=self.profile.basics if self.profile is not None else ProfileBasics(),
            photo_ready=self.photo is not None,
            task=self.profile.task if self.profile is not None else OnboardingTask.FIND_HELP,
            goal=self.goal.goal if self.goal is not None else None,
            help_subjects=self.help_subjects.revision.subjects
            if self.help_subjects is not None
            else HelpSubjects(),
            completed_at=self.lifecycle.completed_at if self.lifecycle is not None else None,
            hidden_at=self.lifecycle.hidden_at if self.lifecycle is not None else None,
        )


class ProfileSetupReader(IdentityReader, Protocol):
    async def setup_snapshot(self, account_id: UUID) -> ProfileSetupSnapshot: ...


class ProfileSetupUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[ProfileSetupReader]: ...


@dataclass(frozen=True, slots=True)
class DiscoveryExposureStatus:
    paused: bool
    can_confirm: bool
    requirements: tuple[RestoreRequirement, ...] = ()


@dataclass(frozen=True, slots=True)
class OnboardingStatus:
    registered: bool
    setup_complete: bool
    capabilities: ProfileCapabilities
    lifecycle: ProfileLifecycle | None
    discovery_exposure: DiscoveryExposureStatus | None = None


@dataclass(frozen=True, slots=True)
class ReadOnboardingStatus:
    unit_of_work: ProfileSetupUnitOfWork
    hasher: SessionHasher

    async def __call__(self, credential: SessionCredential) -> OnboardingStatus:
        async with self.unit_of_work.transaction() as transaction:
            actor, _ = await require_verified_student(
                transaction, await self.hasher.digest(credential)
            )
            snapshot = await transaction.setup_snapshot(actor.session.account_id)
            registered = actor.registration is not None
            exposure = snapshot.exposure
            paused = (
                exposure.effective_pause(await transaction.now()) is not None
                if exposure is not None
                else False
            )
            return OnboardingStatus(
                registered,
                snapshot.lifecycle is not None,
                profile_capabilities(
                    membership=actor.membership,
                    banned=actor.banned,
                    deleted=actor.deleted_at is not None,
                    registered=registered,
                    profile=snapshot.state(),
                ),
                snapshot.lifecycle,
                DiscoveryExposureStatus(
                    paused,
                    paused
                    and registered
                    and snapshot.lifecycle is not None
                    and not snapshot.lifecycle.hidden
                    and not snapshot.state().exposure_requirements,
                    snapshot.state().exposure_requirements if paused else (),
                )
                if exposure is not None
                else None,
            )
