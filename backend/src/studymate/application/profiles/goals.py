import hmac
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID, uuid4

from studymate.application.idempotency import (
    IdempotencyConflictError,
    IntentFingerprinter,
    IntentKey,
)
from studymate.application.identity.sessions import (
    IdentityReader,
    SessionCredential,
    SessionHasher,
    UnauthenticatedError,
    require_verified_student,
)
from studymate.domain.catalogue import Subject
from studymate.domain.study_context import (
    CanonicalSubjectRef,
    CustomSubjectRef,
    GoalContent,
    StudyGoal,
)


class SubjectUnavailableError(Exception):
    pass


class GoalVersionConflictError(Exception):
    def __init__(self, current: "SavedGoal | None") -> None:
        super().__init__("Active study goal has changed")
        self.current_id = current.goal.id if current is not None else None
        self.current_version = current.goal.version if current is not None else 0


@dataclass(frozen=True, slots=True)
class SavedGoal:
    goal: StudyGoal = field(repr=False)
    subject_label: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class GoalIntent:
    fingerprint: bytes = field(repr=False)
    goal_id: UUID
    result_version: int


class GoalTransaction(IdentityReader, Protocol):
    async def active_goal(self, account_id: UUID) -> SavedGoal | None: ...

    async def goal_version(
        self, account_id: UUID, goal_id: UUID, version: int
    ) -> SavedGoal | None: ...

    async def goal_intent(self, account_id: UUID, key: IntentKey) -> GoalIntent | None: ...

    async def subject(self, subject_id: UUID) -> Subject | None: ...

    async def save_goal(self, goal: SavedGoal) -> None: ...

    async def remember_goal_intent(
        self, account_id: UUID, key: IntentKey, intent: GoalIntent, at: datetime
    ) -> None: ...


class GoalUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[GoalTransaction]: ...


@dataclass(frozen=True, slots=True)
class SaveGoalCommand:
    credential: SessionCredential = field(repr=False)
    content: GoalContent = field(repr=False)
    expected_goal_id: UUID | None
    expected_version: int
    intent_key: IntentKey

    def __post_init__(self) -> None:
        if (
            isinstance(self.expected_version, bool)
            or self.expected_version < 0
            or (self.expected_goal_id is None) != (self.expected_version == 0)
        ):
            raise ValueError("Expected goal identity and revision must agree")


@dataclass(frozen=True, slots=True)
class CompleteGoalCommand:
    credential: SessionCredential = field(repr=False)
    goal_id: UUID
    expected_version: int
    intent_key: IntentKey

    def __post_init__(self) -> None:
        if isinstance(self.expected_version, bool) or self.expected_version < 1:
            raise ValueError("Expected goal revision must be positive")


def _expected(current: SavedGoal | None, goal_id: UUID | None, version: int) -> None:
    if (current.goal.id if current is not None else None) != goal_id or (
        current.goal.version if current is not None else 0
    ) != version:
        raise GoalVersionConflictError(current)


async def _replay(
    transaction: GoalTransaction, account_id: UUID, prior: GoalIntent, fingerprint: bytes
) -> SavedGoal:
    if not hmac.compare_digest(prior.fingerprint, fingerprint):
        raise IdempotencyConflictError
    result = await transaction.goal_version(account_id, prior.goal_id, prior.result_version)
    if result is None:
        raise RuntimeError("Saved goal result is unavailable")
    return result


async def _subject_label(
    transaction: GoalTransaction, content: GoalContent, current: SavedGoal | None
) -> str:
    if current is not None and current.goal.content.subject == content.subject:
        return current.subject_label
    if isinstance(content.subject, CustomSubjectRef):
        return content.subject.label
    subject = await transaction.subject(content.subject.id)
    if subject is None or not subject.selectable:
        raise SubjectUnavailableError
    return subject.name


def _parts(command: SaveGoalCommand) -> tuple[str, ...]:
    subject = command.content.subject
    choice = (
        ("canonical", str(subject.id))
        if isinstance(subject, CanonicalSubjectRef)
        else ("custom", subject.label)
    )
    return (
        "goal.save.v1",
        str(command.expected_goal_id),
        str(command.expected_version),
        *choice,
        command.content.topic or "",
        command.content.context or "",
        "1" if command.content.shared_learning else "0",
    )


@dataclass(frozen=True, slots=True)
class SaveOwnGoal:
    unit_of_work: GoalUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(self, command: SaveGoalCommand) -> SavedGoal:
        fingerprint = await self.fingerprinter.fingerprint(_parts(command))
        async with self.unit_of_work.transaction() as transaction:
            actor, now = await require_verified_student(
                transaction, await self.hasher.digest(command.credential)
            )
            account_id = actor.session.account_id
            prior = await transaction.goal_intent(account_id, command.intent_key)
            if prior is not None:
                return await _replay(transaction, account_id, prior, fingerprint)
            current = await transaction.active_goal(account_id)
            _expected(current, command.expected_goal_id, command.expected_version)
            label = await _subject_label(transaction, command.content, current)
            goal = (
                current.goal.revise(command.content, now)
                if current is not None
                else StudyGoal(uuid4(), account_id, 1, command.content, now, now)
            )
            result = SavedGoal(goal, label)
            if current is None or result != current:
                await transaction.save_goal(result)
            await transaction.remember_goal_intent(
                account_id, command.intent_key, GoalIntent(fingerprint, goal.id, goal.version), now
            )
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return result


@dataclass(frozen=True, slots=True)
class CompleteOwnGoal:
    unit_of_work: GoalUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(self, command: CompleteGoalCommand) -> SavedGoal:
        fingerprint = await self.fingerprinter.fingerprint(
            ("goal.complete.v1", str(command.goal_id), str(command.expected_version))
        )
        async with self.unit_of_work.transaction() as transaction:
            actor, now = await require_verified_student(
                transaction, await self.hasher.digest(command.credential)
            )
            account_id = actor.session.account_id
            prior = await transaction.goal_intent(account_id, command.intent_key)
            if prior is not None:
                return await _replay(transaction, account_id, prior, fingerprint)
            current = await transaction.active_goal(account_id)
            if current is None:
                raise GoalVersionConflictError(None)
            _expected(current, command.goal_id, command.expected_version)
            result = SavedGoal(current.goal.complete(now), current.subject_label)
            await transaction.save_goal(result)
            await transaction.remember_goal_intent(
                account_id,
                command.intent_key,
                GoalIntent(fingerprint, result.goal.id, result.goal.version),
                now,
            )
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return result


@dataclass(frozen=True, slots=True)
class ReadOwnGoal:
    unit_of_work: GoalUnitOfWork
    hasher: SessionHasher

    async def __call__(self, credential: SessionCredential) -> SavedGoal | None:
        async with self.unit_of_work.transaction() as transaction:
            actor, _ = await require_verified_student(
                transaction, await self.hasher.digest(credential)
            )
            return await transaction.active_goal(actor.session.account_id)
