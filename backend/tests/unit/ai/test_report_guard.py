"""Queue report guard preserves authority/source failures in the caller transaction."""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.domain.ai.jobs import AiJob, Failure, Versions
from studymate.domain.ai.tasks import ClarifyGoal, Source, TriageReport
from studymate.infrastructure.ai import queue as queue_module
from studymate.infrastructure.ai.queue import SqlAiQueue


@dataclass(slots=True)
class Guard:
    outcome: Failure | None
    calls: list[tuple[AsyncSession, AiJob, bool]] = field(default_factory=list)

    async def check(
        self, session: AsyncSession, job: AiJob, *, lock: bool = True
    ) -> Failure | None:
        self.calls.append((session, job, lock))
        return self.outcome


def triage_job() -> AiJob:
    at = datetime(2026, 11, 12, tzinfo=UTC)
    return AiJob(
        uuid4(),
        uuid4(),
        TriageReport(Source(uuid4(), 1), "Synthetic immutable selected evidence"),
        b"x" * 32,
        Versions("synthetic-model"),
        at,
        at + timedelta(minutes=5),
        at,
    )


@pytest.mark.parametrize("outcome", [None, Failure.ACCOUNT, Failure.STALE_SOURCE])
async def test_report_guard_uses_exact_current_session_and_preserves_failure(
    outcome: Failure | None,
) -> None:
    guard = Guard(outcome)
    queue = SqlAiQueue(async_sessionmaker(), guard)
    job = triage_job()
    async with AsyncSession() as session, session.begin():
        result = await queue._eligible(session, job)
        assert result is outcome
        assert guard.calls == [(session, job, True)]
        assert session.in_transaction()


async def test_absent_report_guard_fails_closed_without_student_authority() -> None:
    queue = SqlAiQueue(async_sessionmaker())
    async with AsyncSession() as session:
        with patch.object(queue_module, "_account", new_callable=AsyncMock) as account:
            assert await queue._eligible(session, triage_job()) is Failure.ACCOUNT
        account.assert_not_awaited()


async def test_student_jobs_keep_actual_student_account_guard() -> None:
    guard = Guard(None)
    queue = SqlAiQueue(async_sessionmaker(), guard)
    job = replace(triage_job(), task=ClarifyGoal(Source(uuid4(), 1), "Synthetic text"))
    async with AsyncSession() as session:
        with patch.object(queue_module, "_account", return_value=False) as account:
            assert await queue._eligible(session, job) is Failure.ACCOUNT
        account.assert_awaited_once_with(session, job.actor_id)
    assert guard.calls == []
