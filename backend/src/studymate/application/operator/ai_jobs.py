"""Audited retained AI metadata search and exact raw business-payload inspection."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from studymate.application.idempotency import IntentFingerprinter
from studymate.application.identity.sessions import SessionCredential, SessionHasher
from studymate.application.operator.ai_ports import (
    OperatorAiCursorCodec,
    OperatorAiFilters,
    OperatorAiPosition,
    OperatorAiTransaction,
    OperatorAiUnitOfWork,
)
from studymate.application.operator.authority import (
    OperatorPrincipal,
    finish_operator,
    require_operator,
)
from studymate.application.operator.cursors import OperatorCursorScope
from studymate.domain.operator.ai_jobs import (
    OPERATOR_AI_PAGE_SIZE,
    OperatorAiJobDetail,
    OperatorAiJobMetadata,
)
from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)


@dataclass(frozen=True, slots=True)
class OperatorAiJobsPage:
    account_id: UUID
    jobs: tuple[OperatorAiJobMetadata, ...]
    next_cursor: str | None
    anchor_created_at: datetime | None
    anchor_job_id: UUID | None
    observed_at: datetime


async def audit_ai_account(
    transaction: OperatorAiTransaction,
    principal: OperatorPrincipal,
    account_id: UUID,
    *,
    found: bool,
) -> None:
    """AI inspections audit their REAL account scope, never a fabricated revision UUID."""
    resource = OperatorResourceRef(OperatorResourceKind.ACCOUNT, account_id)
    await transaction.save_operator_audit(
        OperatorAudit(
            uuid4(),
            principal.access,
            OperatorAction.READ_ACCOUNT,
            resource,
            (resource,) if found else (),
            await transaction.now(),
            OperatorAuditOutcome.READ if found else OperatorAuditOutcome.NOT_FOUND,
        )
    )
    await finish_operator(transaction, principal)


def validate_ai_rows(
    rows: tuple[OperatorAiJobMetadata, ...],
    account_id: UUID,
    filters: OperatorAiFilters,
    position: OperatorAiPosition | None,
) -> None:
    if len(rows) > OPERATOR_AI_PAGE_SIZE + 1:
        raise RuntimeError("AI root source exceeded its bounded metadata page")
    previous = (
        (position.before_created_at, position.before_job_id.int) if position is not None else None
    )
    for row in rows:
        key = row.created_at, row.id.int
        if (
            row.account_id != account_id
            or not filters.matches(row)
            or (previous is not None and key >= previous)
            or (
                position is not None
                and key > (position.anchor_created_at, position.anchor_job_id.int)
            )
        ):
            raise RuntimeError("AI root source violates actual owner, filter or metadata ordering")
        previous = key


@dataclass(frozen=True, slots=True)
class ReadOperatorAiJobs:
    unit_of_work: OperatorAiUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter
    cursor_codec: OperatorAiCursorCodec

    async def __call__(
        self,
        credential: SessionCredential,
        account_id: UUID,
        filters: OperatorAiFilters,
        cursor: str | None = None,
    ) -> OperatorAiJobsPage | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            actual = await transaction.ai_account(account_id)
            if actual is None:
                await audit_ai_account(transaction, principal, account_id, found=False)
                return None
            if actual != account_id:
                raise RuntimeError("AI root account source belongs to another requested account")
            digest = await self.fingerprinter.fingerprint(filters.fingerprint_parts())
            scope = OperatorCursorScope(principal.access.account_id, principal.access.version)
            position = (
                self.cursor_codec.decode(scope, account_id, digest, cursor)
                if cursor is not None
                else None
            )
            rows = await transaction.ai_jobs(account_id, filters, position)
            validate_ai_rows(rows, account_id, filters, position)
            anchor_at, anchor_id = (
                (position.anchor_created_at, position.anchor_job_id)
                if position is not None
                else (rows[0].created_at, rows[0].id)
                if rows
                else (None, None)
            )
            visible = rows[:OPERATOR_AI_PAGE_SIZE]
            continuation = None
            if len(rows) > OPERATOR_AI_PAGE_SIZE:
                if anchor_at is None or anchor_id is None:
                    raise RuntimeError("AI root source lost its actual continuation anchor")
                continuation = self.cursor_codec.encode(
                    scope,
                    account_id,
                    digest,
                    OperatorAiPosition(
                        anchor_at, anchor_id, visible[-1].created_at, visible[-1].id
                    ),
                )
            observed = await transaction.now()
            await audit_ai_account(transaction, principal, account_id, found=True)
            return OperatorAiJobsPage(
                account_id, visible, continuation, anchor_at, anchor_id, observed
            )


@dataclass(frozen=True, slots=True)
class OperatorAiJobInspection:
    detail: OperatorAiJobDetail = field(repr=False)
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class ReadOperatorAiJob:
    unit_of_work: OperatorAiUnitOfWork
    hasher: SessionHasher

    async def __call__(
        self,
        credential: SessionCredential,
        account_id: UUID,
        job_id: UUID,
    ) -> OperatorAiJobInspection | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            actual = await transaction.ai_account(account_id)
            if actual is None:
                await audit_ai_account(transaction, principal, account_id, found=False)
                return None
            if actual != account_id:
                raise RuntimeError(
                    "AI detail account source differs from its requested actual owner"
                )
            detail = await transaction.ai_job(account_id, job_id)
            if detail is not None and (
                detail.job.account_id != account_id or detail.job.id != job_id
            ):
                raise RuntimeError(
                    "AI detail source differs from its requested actual owner or job"
                )
            # Actual parent ACCOUNT was read even when its owned child was absent/foreign.
            observed_at = await transaction.now()
            await audit_ai_account(transaction, principal, account_id, found=True)
            return OperatorAiJobInspection(detail, observed_at) if detail is not None else None
