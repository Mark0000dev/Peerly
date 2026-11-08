from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest

from studymate.application.ai.ports import (
    Admission,
    AiJobNotFoundError,
    AiTransaction,
    StudentSubmission,
)
from studymate.application.ai.student import CancelStudentJob, SubmitStudentJob
from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.domain.ai.jobs import AiJob, Versions
from studymate.domain.ai.tasks import AiKind, AiTask, ClarifyGoal, Source
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.identity_store import CREDENTIAL, IdentityStore


class Store(IdentityStore):
    def __init__(self) -> None:
        super().__init__()
        self.jobs: dict[UUID, AiJob] = {}
        self.expire_after_write = False

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AiTransaction]:
        before = self.jobs.copy()
        try:
            yield self
        except BaseException:
            self.jobs = before
            raise

    async def replay(
        self, actor_id: UUID, kind: AiKind, key: IntentKey, digest: bytes
    ) -> AiJob | None:
        assert actor_id == self.actor.session.account_id
        assert kind == AiKind.CLARIFY_GOAL
        assert key.value
        assert len(digest) == len(b"x" * 32)
        return None

    async def prepare(self, actor_id: UUID, submission: StudentSubmission) -> AiTask:
        assert actor_id == self.actor.session.account_id
        assert submission.text is not None
        assert isinstance(submission.source, Source)
        return ClarifyGoal(submission.source, submission.text)

    async def admit(self, intent: Admission, at: datetime) -> AiJob:
        job = AiJob(
            uuid4(),
            intent.actor_id,
            intent.task,
            intent.digest,
            intent.versions,
            at,
            at + timedelta(minutes=5),
            at,
        )
        self.jobs[job.id] = job
        if self.expire_after_write:
            self.clock = self.actor.session.expires_at
        return job

    async def owned(self, actor_id: UUID, job_id: UUID, *, cancel: bool = False) -> AiJob:
        job = self.jobs.get(job_id)
        if job is None or job.actor_id != actor_id:
            raise AiJobNotFoundError
        if cancel:
            job = job.cancel()
            self.jobs[job.id] = job
            if self.expire_after_write:
                self.clock = self.actor.session.expires_at
        return job


def submit(store: Store) -> SubmitStudentJob:
    return SubmitStudentJob(
        store, Sha256SessionHasher(), HmacIntentFingerprinter(b"x" * 32), Versions("synthetic")
    )


def request() -> StudentSubmission:
    return StudentSubmission(AiKind.CLARIFY_GOAL, Source(uuid4(), 1), "Synthetic explicit text")


async def test_session_expiry_before_submit_commit_rolls_back_admission() -> None:
    store = Store()
    store.expire_after_write = True
    with pytest.raises(UnauthenticatedError):
        await submit(store)(CREDENTIAL, request(), IntentKey(str(uuid4())))
    assert store.jobs == {}


async def test_session_expiry_before_cancel_commit_rolls_back_cancellation() -> None:
    store = Store()
    created = await submit(store)(CREDENTIAL, request(), IntentKey(str(uuid4())))
    store.expire_after_write = True
    with pytest.raises(UnauthenticatedError):
        await CancelStudentJob(store, Sha256SessionHasher())(CREDENTIAL, created.id)
    assert store.jobs[created.id] == created
