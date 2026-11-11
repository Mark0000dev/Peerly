from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from studymate.application.discovery.cursors import (
    DiscoveryCursor,
    DiscoveryCursorCodec,
    DiscoveryView,
)
from studymate.application.discovery.profiles import (
    DiscoveryProfileReader,
    DiscoveryProfileSource,
    profile_declarations,
)
from studymate.application.identity.sessions import (
    SessionCredential,
    SessionHasher,
    StudentActionDeniedError,
    UnauthenticatedError,
    require_verified_student,
)
from studymate.application.profiles.goals import SavedGoal
from studymate.application.profiles.help_subjects import SavedHelpSubjects
from studymate.domain.discovery import DiscoveryMatch, DiscoveryMode, discovery_match
from studymate.domain.discovery_context import DiscoveryContext, discovery_context
from studymate.domain.discovery_order import DiscoveryPosition
from studymate.domain.discovery_passes import PrivatePassRevision
from studymate.domain.media import PhotoRevision
from studymate.domain.profiles import ProfileRevision

DISCOVERY_PAGE_SIZE = 20


class DiscoveryEmptyReason(StrEnum):
    CONTEXT_REQUIRED = "context_required"
    NO_RELEVANT_PEOPLE = "no_relevant_people"
    EXHAUSTED = "exhausted"
    NO_AVAILABLE_PASSED_PEOPLE = "no_available_passed_people"


@dataclass(frozen=True, slots=True)
class CandidateSource:
    source: DiscoveryProfileSource = field(repr=False)
    position: DiscoveryPosition
    own_pass: PrivatePassRevision | None = None

    def __post_init__(self) -> None:
        if self.source.setup.account_id != self.position.person_id:
            raise ValueError("Candidate ordering must belong to its scoped source")


@dataclass(frozen=True, slots=True)
class DiscoveryCard:
    profile: ProfileRevision = field(repr=False)
    photo: PhotoRevision
    goal: SavedGoal | None = field(repr=False)
    help_subjects: SavedHelpSubjects | None = field(repr=False)
    match: DiscoveryMatch
    own_pass: PrivatePassRevision | None


@dataclass(frozen=True, slots=True)
class DiscoveryPage:
    context: DiscoveryContext | None
    people: tuple[DiscoveryCard, ...]
    next_cursor: str | None
    empty_reason: DiscoveryEmptyReason | None
    undo_pass: PrivatePassRevision | None = None


class DiscoveryDeckReader(DiscoveryProfileReader, Protocol):
    async def latest_undo_pass(self, context: DiscoveryContext) -> PrivatePassRevision | None: ...

    async def candidates(
        self,
        context: DiscoveryContext,
        view: DiscoveryView,
        cursor: DiscoveryCursor | None,
        as_of: datetime,
        limit: int,
    ) -> tuple[CandidateSource, ...]:
        """Bounded bulk projection; filters live pair/lifecycle/pass facts in SQL."""
        ...

    async def has_context_people(self, context: DiscoveryContext, at: datetime) -> bool:
        """Actual relevant eligible sources before private passes/request exclusions."""
        ...


class DiscoveryDeckUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[DiscoveryDeckReader]: ...


def _card(
    own: DiscoveryProfileSource, row: CandidateSource, context: DiscoveryContext, at: datetime
) -> DiscoveryCard | None:
    target = row.source
    setup = target.setup
    if setup.account_id == own.setup.account_id or not target.can_make_new_contacts:
        return None
    if setup.exposure is None or setup.exposure.effective_pause(at) is not None:
        return None
    if setup.profile is None or setup.photo is None:
        return None
    match = discovery_match(profile_declarations(own), profile_declarations(target), context.mode)
    if match is None:
        return None
    goal = setup.goal if setup.goal is not None and setup.goal.goal.active else None
    if row.own_pass is not None and (
        row.own_pass.context != context or row.own_pass.target_id != setup.account_id
    ):
        raise RuntimeError("Candidate pass state belongs to another private context")
    return DiscoveryCard(setup.profile, setup.photo, goal, setup.help_subjects, match, row.own_pass)


async def _empty_reason(
    transaction: DiscoveryDeckReader, context: DiscoveryContext, view: DiscoveryView, at: datetime
) -> DiscoveryEmptyReason:
    if view == DiscoveryView.PASSED:
        return DiscoveryEmptyReason.NO_AVAILABLE_PASSED_PEOPLE
    has_people = await transaction.has_context_people(context, at)
    return DiscoveryEmptyReason.EXHAUSTED if has_people else DiscoveryEmptyReason.NO_RELEVANT_PEOPLE


@dataclass(frozen=True, slots=True)
class ReadDiscoveryDeck:
    unit_of_work: DiscoveryDeckUnitOfWork
    hasher: SessionHasher
    cursor_codec: DiscoveryCursorCodec

    async def __call__(
        self,
        credential: SessionCredential,
        mode: DiscoveryMode,
        view: DiscoveryView = DiscoveryView.CANDIDATES,
        cursor: str | None = None,
    ) -> DiscoveryPage:
        async with self.unit_of_work.transaction() as transaction:
            actor, now = await require_verified_student(
                transaction, await self.hasher.digest(credential)
            )
            own = await transaction.profile_source(actor.session.account_id)
            if not actor.activation_complete or own is None or not own.can_make_new_contacts:
                raise StudentActionDeniedError
            if own.setup.account_id != actor.session.account_id:
                raise RuntimeError("Discovery source belongs to another actor")
            context = discovery_context(
                actor.session.account_id,
                mode,
                own.setup.goal.goal if own.setup.goal is not None else None,
                own.setup.help_subjects.revision if own.setup.help_subjects is not None else None,
            )
            if context is None:
                if not actor.session.is_active(await transaction.now()):
                    raise UnauthenticatedError
                return DiscoveryPage(None, (), None, DiscoveryEmptyReason.CONTEXT_REQUIRED)
            decoded = (
                self.cursor_codec.decode(context, view, cursor, now) if cursor is not None else None
            )
            as_of = decoded.as_of if decoded is not None else now
            rows = await transaction.candidates(
                context, view, decoded, as_of, DISCOVERY_PAGE_SIZE + 1
            )
            if len(rows) > DISCOVERY_PAGE_SIZE + 1:
                raise RuntimeError("Discovery reader exceeded its bounded page")
            observed_at = await transaction.now()
            scanned = rows[:DISCOVERY_PAGE_SIZE]
            people = tuple(
                card
                for row in scanned
                if (card := _card(own, row, context, observed_at)) is not None
            )
            next_cursor = (
                self.cursor_codec.encode(
                    context, view, DiscoveryCursor(as_of, scanned[-1].position)
                )
                if len(rows) > DISCOVERY_PAGE_SIZE
                else None
            )
            reason = None
            if not people and next_cursor is None:
                reason = await _empty_reason(transaction, context, view, observed_at)
            undo_pass = await transaction.latest_undo_pass(context)
            if undo_pass is not None and (undo_pass.context != context or not undo_pass.passed):
                raise RuntimeError("Latest Undo belongs to another private context")
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return DiscoveryPage(context, people, next_cursor, reason, undo_pass)
