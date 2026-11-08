from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID, uuid4

from studymate.application.identity.sessions import (
    IdentityReader,
    IdentitySnapshot,
    SessionCredential,
    SessionHasher,
    StudentActionDeniedError,
    UnauthenticatedError,
    require_verified_student,
)
from studymate.application.profiles.goals import SavedGoal
from studymate.application.profiles.help_subjects import SavedHelpSubjects
from studymate.application.profiles.onboarding import ProfileSetupSnapshot
from studymate.application.safety.blocks import OwnBlockResult
from studymate.domain.discovery import StudyDeclarations
from studymate.domain.media import PhotoRevision
from studymate.domain.membership import Membership
from studymate.domain.profile_readiness import profile_capabilities
from studymate.domain.profiles import ProfileRevision
from studymate.domain.reports import ProfileAccessContext, ProfileVersionRefs
from studymate.domain.study_context import HelpSubjects


class DiscoveryProfileUnavailableError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class DiscoveryProfileSource:
    setup: ProfileSetupSnapshot = field(repr=False)
    membership: Membership | None = field(repr=False)
    registered: bool
    banned: bool
    deleted: bool

    def __post_init__(self) -> None:
        account_id = self.setup.account_id
        components = (
            self.setup.profile,
            self.setup.photo,
            self.setup.lifecycle,
            self.setup.exposure,
        )
        if any(part is not None and part.account_id != account_id for part in components):
            raise ValueError("Profile components must belong to their scoped account")
        if self.setup.goal is not None and self.setup.goal.goal.account_id != account_id:
            raise ValueError("Profile goal must belong to its scoped account")
        if (
            self.setup.help_subjects is not None
            and self.setup.help_subjects.revision.account_id != account_id
        ):
            raise ValueError("Profile help declarations must belong to their scoped account")

    @property
    def can_make_new_contacts(self) -> bool:
        return profile_capabilities(
            membership=self.membership,
            banned=self.banned,
            deleted=self.deleted,
            registered=self.registered,
            profile=self.setup.state(),
        ).can_make_new_contacts


def profile_declarations(source: DiscoveryProfileSource) -> StudyDeclarations:
    setup = source.setup
    return StudyDeclarations(
        setup.account_id,
        setup.goal.goal if setup.goal is not None else None,
        setup.help_subjects.revision.subjects
        if setup.help_subjects is not None
        else HelpSubjects(),
    )


@dataclass(frozen=True, slots=True)
class DiscoveryProfile:
    access_context: ProfileAccessContext = field(repr=False)
    profile: ProfileRevision = field(repr=False)
    photo: PhotoRevision
    goal: SavedGoal | None = field(repr=False)
    help_subjects: SavedHelpSubjects | None = field(repr=False)
    own_block: OwnBlockResult


class DiscoveryProfileReader(IdentityReader, Protocol):
    async def profile_source(self, account_id: UUID) -> DiscoveryProfileSource | None: ...

    async def pair_blocked(self, actor_id: UUID, target_id: UUID) -> bool: ...


class DiscoveryProfileTransaction(DiscoveryProfileReader, Protocol):
    async def own_block_state(self, actor_id: UUID, target_id: UUID) -> OwnBlockResult: ...

    async def remember_profile_access(self, context: ProfileAccessContext) -> None: ...


class DiscoveryProfileUnitOfWork(Protocol):
    def transaction(
        self, target_id: UUID
    ) -> AbstractAsyncContextManager[DiscoveryProfileTransaction]: ...


async def authorize_discovery_profile(
    transaction: DiscoveryProfileReader,
    credential: SessionCredential,
    hasher: SessionHasher,
    target_id: UUID,
) -> tuple[IdentitySnapshot, DiscoveryProfileSource]:
    actor, _ = await require_verified_student(transaction, await hasher.digest(credential))
    actor_id = actor.session.account_id
    if not actor.activation_complete:
        raise StudentActionDeniedError
    own = await transaction.profile_source(actor_id)
    if own is None or not own.can_make_new_contacts:
        raise StudentActionDeniedError
    if actor_id == target_id:
        raise DiscoveryProfileUnavailableError
    target = await transaction.profile_source(target_id)
    if target is None or not target.can_make_new_contacts:
        raise DiscoveryProfileUnavailableError
    if own.setup.account_id != actor_id or target.setup.account_id != target_id:
        raise RuntimeError("Profile source belongs to another account")
    if await transaction.pair_blocked(actor_id, target_id):
        raise DiscoveryProfileUnavailableError
    return actor, target


@dataclass(frozen=True, slots=True)
class ReadDiscoveryProfile:
    unit_of_work: DiscoveryProfileUnitOfWork
    hasher: SessionHasher

    async def __call__(self, credential: SessionCredential, target_id: UUID) -> DiscoveryProfile:
        async with self.unit_of_work.transaction(target_id) as transaction:
            actor, target = await authorize_discovery_profile(
                transaction, credential, self.hasher, target_id
            )
            actor_id = actor.session.account_id
            profile, photo = target.setup.profile, target.setup.photo
            if profile is None or photo is None:
                raise DiscoveryProfileUnavailableError
            goal = target.setup.goal
            if goal is not None and not goal.goal.active:
                goal = None
            help_subjects = target.setup.help_subjects
            own_block = await transaction.own_block_state(actor_id, target_id)
            if own_block.target_id != target_id:
                raise RuntimeError("Own block projection belongs to another peer")
            if own_block.blocked:
                raise DiscoveryProfileUnavailableError
            now = await transaction.now()
            context = ProfileAccessContext(
                uuid4(),
                actor_id,
                ProfileVersionRefs(
                    target_id,
                    profile.version,
                    photo.version,
                    goal.goal.id if goal is not None else None,
                    goal.goal.version if goal is not None else None,
                    help_subjects.revision.version if help_subjects is not None else None,
                ),
                now,
            )
            await transaction.remember_profile_access(context)
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return DiscoveryProfile(context, profile, photo, goal, help_subjects, own_block)
