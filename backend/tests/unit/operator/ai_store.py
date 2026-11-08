from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID

from studymate.application.operator.ai_ports import OperatorAiFilters, OperatorAiPosition
from studymate.domain.ai.jobs import JobState
from studymate.domain.ai.tasks import AiKind
from studymate.domain.operator.ai_jobs import (
    OPERATOR_AI_PAGE_SIZE,
    OperatorAiJobDetail,
    OperatorAiJobMetadata,
    OperatorAiVersions,
)
from studymate.domain.operator.timeline import OperatorEventOrigin
from tests.unit.identity_store import NOW
from tests.unit.operator.store import TARGET, Store

JOB = UUID(int=1001)
DIGEST = bytes(range(32))
RAW_INPUT = '  { "legacy_payload": "Private retained goal text" }\n'
RAW_RESULT = "not current JSON: private old result"


def metadata(job_id: UUID = JOB, account_id: UUID = TARGET) -> OperatorAiJobMetadata:
    return OperatorAiJobMetadata(
        job_id,
        account_id,
        AiKind.CLARIFY_GOAL,
        JobState.SUCCEEDED,
        UUID(int=1002),
        7,
        NOW - timedelta(days=1),
        NOW - timedelta(hours=1),
        NOW,
        0,
        None,
        OperatorAiVersions(
            " retired model ", " legacy prompt ", " unsupported schema ", "old-adapter"
        ),
        OperatorEventOrigin(),
    )


def detail(job_id: UUID = JOB, account_id: UUID = TARGET) -> OperatorAiJobDetail:
    return OperatorAiJobDetail(metadata(job_id, account_id), DIGEST, RAW_INPUT, RAW_RESULT, ())


class AiStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.accounts = {TARGET}
        self.rows = {JOB: metadata()}
        self.job_details = {JOB: detail()}
        self.account_override: UUID | None = None
        self.list_override: tuple[OperatorAiJobMetadata, ...] | None = None
        self.detail_override: OperatorAiJobDetail | None = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["AiStore"]:
        async with Store.transaction(self):
            yield self

    async def ai_account(self, account_id: UUID) -> UUID | None:
        self.queried()
        return (
            self.account_override
            if self.account_override is not None
            else account_id
            if account_id in self.accounts
            else None
        )

    async def ai_jobs(
        self, account_id: UUID, filters: OperatorAiFilters, position: OperatorAiPosition | None
    ) -> tuple[OperatorAiJobMetadata, ...]:
        self.queried()
        if self.list_override is not None:
            return self.list_override
        rows = (
            row
            for row in self.rows.values()
            if row.account_id == account_id
            and filters.matches(row)
            and (
                position is None
                or (
                    (row.created_at, row.id.int)
                    <= (position.anchor_created_at, position.anchor_job_id.int)
                    and (row.created_at, row.id.int)
                    < (position.before_created_at, position.before_job_id.int)
                )
            )
        )
        return tuple(sorted(rows, key=lambda row: (row.created_at, row.id.int), reverse=True))[
            : OPERATOR_AI_PAGE_SIZE + 1
        ]

    async def ai_job(self, account_id: UUID, job_id: UUID) -> OperatorAiJobDetail | None:
        self.queried()
        if self.detail_override is not None:
            return self.detail_override
        value = self.job_details.get(job_id)
        return value if value is not None and value.job.account_id == account_id else None
