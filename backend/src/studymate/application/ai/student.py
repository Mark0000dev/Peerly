from dataclasses import dataclass
from uuid import UUID

from studymate.application.ai.ports import (
    Admission,
    AiUnavailableError,
    AiUnitOfWork,
    StudentSubmission,
)
from studymate.application.idempotency import IntentFingerprinter, IntentKey
from studymate.application.identity.sessions import (
    SessionCredential,
    SessionHasher,
    UnauthenticatedError,
    require_verified_student,
)
from studymate.domain.ai.jobs import AiJob, Versions


@dataclass(frozen=True, slots=True)
class SubmitStudentJob:
    unit_of_work: AiUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter
    versions: Versions

    async def __call__(
        self,
        credential: SessionCredential,
        submission: StudentSubmission,
        key: IntentKey,
        *,
        accepting: bool = True,
    ) -> AiJob:
        # Fingerprint the explicit intent, not a mutable catalogue rendering.
        digest = await self.fingerprinter.fingerprint(
            (
                "ai.submit.v2",
                submission.source.kind,
                submission.kind.value,
                str(submission.source.id),
                str(submission.source.version),
                submission.text or "",
                submission.target.value,
                submission.label or "",
                *(str(value) for value in submission.candidate_ids),
            )
        )
        async with self.unit_of_work.transaction() as transaction:
            actor, now = await require_verified_student(
                transaction, await self.hasher.digest(credential)
            )
            if not accepting:
                raise AiUnavailableError
            prior = await transaction.replay(actor.session.account_id, submission.kind, key, digest)
            if prior is not None:
                return prior
            task = await transaction.prepare(actor.session.account_id, submission)
            result = await transaction.admit(
                Admission(actor.session.account_id, task, key, digest, self.versions), now
            )
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return result


@dataclass(frozen=True, slots=True)
class ReadStudentJob:
    unit_of_work: AiUnitOfWork
    hasher: SessionHasher

    async def __call__(self, credential: SessionCredential, job_id: UUID) -> AiJob:
        async with self.unit_of_work.transaction() as transaction:
            actor, _ = await require_verified_student(
                transaction, await self.hasher.digest(credential)
            )
            return await transaction.owned(actor.session.account_id, job_id)


@dataclass(frozen=True, slots=True)
class CancelStudentJob:
    unit_of_work: AiUnitOfWork
    hasher: SessionHasher

    async def __call__(self, credential: SessionCredential, job_id: UUID) -> AiJob:
        async with self.unit_of_work.transaction() as transaction:
            actor, _ = await require_verified_student(
                transaction, await self.hasher.digest(credential)
            )
            result = await transaction.owned(actor.session.account_id, job_id, cancel=True)
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return result
