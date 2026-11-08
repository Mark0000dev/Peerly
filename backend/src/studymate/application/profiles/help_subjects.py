import hmac
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

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
from studymate.application.profiles.goals import SubjectUnavailableError
from studymate.domain.catalogue import Subject
from studymate.domain.study_context import HelpRevision, HelpSubjects


class HelpVersionConflictError(Exception):
    def __init__(self, version: int) -> None:
        super().__init__("Help subjects have changed")
        self.current_version = version


@dataclass(frozen=True, slots=True)
class SavedHelpSubjects:
    revision: HelpRevision = field(repr=False)
    labels: tuple[str, ...] = field(repr=False)

    def __post_init__(self) -> None:
        if len(self.labels) != len(self.revision.subjects.values):
            raise ValueError("Help labels must correspond to selected subjects")


@dataclass(frozen=True, slots=True)
class HelpIntent:
    fingerprint: bytes = field(repr=False)
    result_version: int


class HelpTransaction(IdentityReader, Protocol):
    async def help_subjects(
        self, account_id: UUID, version: int | None = None
    ) -> SavedHelpSubjects | None: ...

    async def help_intent(self, account_id: UUID, key: IntentKey) -> HelpIntent | None: ...

    async def subjects(self, subject_ids: tuple[UUID, ...]) -> tuple[Subject, ...]: ...

    async def save_help(self, value: SavedHelpSubjects) -> None: ...

    async def remember_help_intent(
        self, account_id: UUID, key: IntentKey, intent: HelpIntent, at: datetime
    ) -> None: ...


class HelpUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[HelpTransaction]: ...


@dataclass(frozen=True, slots=True)
class SaveHelpCommand:
    credential: SessionCredential = field(repr=False)
    subjects: HelpSubjects = field(repr=False)
    expected_version: int
    intent_key: IntentKey

    def __post_init__(self) -> None:
        if isinstance(self.expected_version, bool) or self.expected_version < 0:
            raise ValueError("Expected help version must be nonnegative")


async def _labels(
    transaction: HelpTransaction, requested: HelpSubjects, current: SavedHelpSubjects | None
) -> tuple[str, ...]:
    existing = (
        dict(
            zip(
                (item.subject_id for item in current.revision.subjects.values),
                current.labels,
                strict=True,
            )
        )
        if current is not None
        else {}
    )
    wanted = tuple(item.subject_id for item in requested.values if item.subject_id not in existing)
    found = {subject.id: subject for subject in await transaction.subjects(wanted)}
    selected = existing.copy()
    for subject_id in wanted:
        subject = found.get(subject_id)
        if subject is None or not subject.selectable:
            raise SubjectUnavailableError
        selected[subject_id] = subject.name
    return tuple(selected[item.subject_id] for item in requested.values)


@dataclass(frozen=True, slots=True)
class SaveOwnHelpSubjects:
    unit_of_work: HelpUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(self, command: SaveHelpCommand) -> SavedHelpSubjects:
        fingerprint = await self.fingerprinter.fingerprint(
            (
                "help.save.v1",
                str(command.expected_version),
                *(
                    part
                    for item in command.subjects.values
                    for part in (str(item.subject_id), item.topic_note or "")
                ),
            )
        )
        async with self.unit_of_work.transaction() as transaction:
            actor, now = await require_verified_student(
                transaction, await self.hasher.digest(command.credential)
            )
            account_id = actor.session.account_id
            prior = await transaction.help_intent(account_id, command.intent_key)
            if prior is not None:
                if not hmac.compare_digest(prior.fingerprint, fingerprint):
                    raise IdempotencyConflictError
                result = await transaction.help_subjects(account_id, prior.result_version)
                if result is None:
                    raise RuntimeError("Saved help result is unavailable")
                return result
            current = await transaction.help_subjects(account_id)
            version = current.revision.version if current is not None else 0
            if command.expected_version != version:
                raise HelpVersionConflictError(version)
            labels = await _labels(transaction, command.subjects, current)
            if current is not None and current.revision.subjects == command.subjects:
                result = current
            else:
                result = SavedHelpSubjects(
                    HelpRevision(account_id, version + 1, command.subjects, now), labels
                )
                await transaction.save_help(result)
            await transaction.remember_help_intent(
                account_id,
                command.intent_key,
                HelpIntent(fingerprint, result.revision.version),
                now,
            )
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return result


@dataclass(frozen=True, slots=True)
class ReadOwnHelpSubjects:
    unit_of_work: HelpUnitOfWork
    hasher: SessionHasher

    async def __call__(self, credential: SessionCredential) -> SavedHelpSubjects | None:
        async with self.unit_of_work.transaction() as transaction:
            actor, _ = await require_verified_student(
                transaction, await self.hasher.digest(credential)
            )
            return await transaction.help_subjects(actor.session.account_id)
