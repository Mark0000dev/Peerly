"""Narrow internal replay override; ordinary student AI ownership rules stay unchanged."""

import hmac
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import select

from studymate.application.ai.ports import AiUnavailableError
from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.domain.ai.jobs import AiJob, Versions
from studymate.domain.ai.tasks import AiKind, TriageReport
from studymate.domain.operator.access import OperatorAccess
from studymate.infrastructure.ai.models import AiIntentRecord, AiJobRecord
from studymate.infrastructure.ai.persistence import SqlAiTransaction, job_value, lock_slot
from studymate.infrastructure.ai.runtime.availability import require_runtime_ready
from studymate.infrastructure.ai.runtime.health import REPORT_GUARD_VERSION


class InternalTriageScope(Protocol):
    @property
    def report_id(self) -> UUID: ...

    def checked_triage_actor(self) -> OperatorAccess: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class SqlOperatorTriageAdmission(SqlAiTransaction):
    scope: InternalTriageScope

    async def runtime_versions(self, at: datetime) -> Versions:
        del at  # Re-read the actual database clock after acquiring the slot lock.
        self.scope.checked_triage_actor()
        slot = await lock_slot(self.session)
        versions = require_runtime_ready(slot, await self.now())
        if slot.runtime_report_guard_version != REPORT_GUARD_VERSION:
            raise AiUnavailableError
        return versions

    async def replay(
        self, actor_id: UUID, kind: AiKind, key: IntentKey, digest: bytes
    ) -> AiJob | None:
        if kind != AiKind.TRIAGE_REPORT or actor_id != self.scope.checked_triage_actor().account_id:
            raise RuntimeError("Internal triage replay lacks its actual current operator scope")
        prior = await self.session.get(AiIntentRecord, (actor_id, kind.value, key.value))
        if prior is None:
            return None
        if not hmac.compare_digest(prior.digest, digest):
            raise IdempotencyConflictError
        row = (
            await self.session.scalars(
                select(AiJobRecord).where(
                    AiJobRecord.id == prior.job_id,
                    AiJobRecord.actor_id == actor_id,
                    AiJobRecord.kind == AiKind.TRIAGE_REPORT.value,
                    AiJobRecord.source_id == self.scope.report_id,
                )
            )
        ).one_or_none()
        if row is None:
            raise RuntimeError("Internal triage receipt differs from its actual actor/report/job")
        job = job_value(row)
        if not isinstance(job.task, TriageReport):
            raise RuntimeError("Internal triage receipt contains another actual AI task kind")
        return job
