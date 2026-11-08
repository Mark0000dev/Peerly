"""Explicit retained AI projections; never load executor tokens/intents or decode current tasks."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import load_only

from studymate.application.operator.ai_ports import OperatorAiFilters, OperatorAiPosition
from studymate.domain.ai.jobs import Failure, JobState
from studymate.domain.ai.tasks import AiKind
from studymate.domain.operator.ai_jobs import (
    OPERATOR_AI_MAX_ATTEMPTS,
    OPERATOR_AI_PAGE_SIZE,
    OperatorAiAttempt,
    OperatorAiAttemptOutcome,
    OperatorAiJobDetail,
    OperatorAiJobMetadata,
    OperatorAiVersions,
)
from studymate.domain.operator.timeline import OperatorEventOrigin
from studymate.infrastructure.ai.models import AiAttemptRecord, AiJobRecord
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.transactions import open_transaction

METADATA_COLUMNS = (
    AiJobRecord.id,
    AiJobRecord.actor_id,
    AiJobRecord.kind,
    AiJobRecord.state,
    AiJobRecord.source_id,
    AiJobRecord.source_version,
    AiJobRecord.created_at,
    AiJobRecord.deadline,
    AiJobRecord.not_before,
    AiJobRecord.attempts,
    AiJobRecord.failure,
    AiJobRecord.model,
    AiJobRecord.prompt,
    AiJobRecord.schema_version,
    AiJobRecord.adapter,
    AiJobRecord.request_id,
    AiJobRecord.action_id,
    AiJobRecord.trace_id,
    AiJobRecord.span_id,
)


def metadata_value(row: AiJobRecord) -> OperatorAiJobMetadata:
    return OperatorAiJobMetadata(
        row.id,
        row.actor_id,
        AiKind(row.kind),
        JobState(row.state),
        row.source_id,
        row.source_version,
        row.created_at,
        row.deadline,
        row.not_before,
        row.attempts,
        Failure(row.failure) if row.failure is not None else None,
        OperatorAiVersions(row.model, row.prompt, row.schema_version, row.adapter),
        OperatorEventOrigin(row.request_id, row.action_id, row.trace_id, row.span_id),
    )


@dataclass(frozen=True, slots=True)
class SqlOperatorAiTransaction(SqlOperatorTransaction):
    async def ai_account(self, account_id: UUID) -> UUID | None:
        self.checked_access()
        return await self.session.scalar(
            select(AccountRecord.id).where(AccountRecord.id == account_id)
        )

    async def ai_jobs(
        self, account_id: UUID, filters: OperatorAiFilters, position: OperatorAiPosition | None
    ) -> tuple[OperatorAiJobMetadata, ...]:
        self.checked_access()
        statement = (
            select(AiJobRecord)
            .options(load_only(*METADATA_COLUMNS, raiseload=True))
            .where(AiJobRecord.actor_id == account_id)
        )
        if filters.kind is not None:
            statement = statement.where(AiJobRecord.kind == filters.kind.value)
        if filters.state is not None:
            statement = statement.where(AiJobRecord.state == filters.state.value)
        if filters.created_from is not None:
            statement = statement.where(AiJobRecord.created_at >= filters.created_from)
        if filters.created_before is not None:
            statement = statement.where(AiJobRecord.created_at < filters.created_before)
        if position is not None:
            statement = statement.where(
                tuple_(AiJobRecord.created_at, AiJobRecord.id)
                <= tuple_(position.anchor_created_at, position.anchor_job_id),
                tuple_(AiJobRecord.created_at, AiJobRecord.id)
                < tuple_(position.before_created_at, position.before_job_id),
            )
        rows = await self.session.scalars(
            statement.order_by(AiJobRecord.created_at.desc(), AiJobRecord.id.desc()).limit(
                OPERATOR_AI_PAGE_SIZE + 1
            )
        )
        return tuple(metadata_value(row) for row in rows)

    async def ai_job(self, account_id: UUID, job_id: UUID) -> OperatorAiJobDetail | None:
        self.checked_access()
        row = await self.session.scalar(
            select(AiJobRecord)
            .options(
                load_only(
                    *METADATA_COLUMNS,
                    AiJobRecord.digest,
                    AiJobRecord.input_json,
                    AiJobRecord.result_json,
                    raiseload=True,
                )
            )
            .where(AiJobRecord.actor_id == account_id, AiJobRecord.id == job_id)
        )
        if row is None:
            return None
        attempts = await self.session.scalars(
            select(AiAttemptRecord)
            .options(
                load_only(
                    AiAttemptRecord.job_id,
                    AiAttemptRecord.number,
                    AiAttemptRecord.started_at,
                    AiAttemptRecord.ended_at,
                    AiAttemptRecord.outcome,
                    raiseload=True,
                )
            )
            .join(AiJobRecord, AiJobRecord.id == AiAttemptRecord.job_id)
            .where(
                AiJobRecord.actor_id == account_id,
                AiJobRecord.id == job_id,
            )
            .order_by(AiAttemptRecord.number)
            .limit(OPERATOR_AI_MAX_ATTEMPTS + 1)
        )
        return OperatorAiJobDetail(
            metadata_value(row),
            row.digest,
            row.input_json,
            row.result_json,
            tuple(
                OperatorAiAttempt(
                    attempt.job_id,
                    attempt.number,
                    attempt.started_at,
                    attempt.ended_at,
                    OperatorAiAttemptOutcome(attempt.outcome)
                    if attempt.outcome is not None
                    else None,
                )
                for attempt in attempts
            ),
        )


@dataclass(frozen=True, slots=True)
class SqlOperatorAiUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: OperatorAuditRecorder

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlOperatorAiTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlOperatorAiTransaction(session, self.recorder)
