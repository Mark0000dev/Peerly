from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.support.cases import SupportIntent
from studymate.application.support.operator import OperatorSupportCase
from studymate.domain.operator.access import OperatorAccess
from studymate.domain.support.cases import SupportContent, SupportReceipt, SupportTopic
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.transactions import open_transaction
from studymate.infrastructure.support.models import (
    SupportCaseRecord,
    SupportOperatorIntentRecord,
    SupportRevisionRecord,
)
from studymate.infrastructure.support.persistence import SupportEventRecorder, receipt


@dataclass(frozen=True, slots=True)
class SqlOperatorSupportTransaction(SqlOperatorTransaction):
    record_event: SupportEventRecorder = field(kw_only=True)

    async def case(self, case_id: UUID) -> OperatorSupportCase | None:
        case = await self.session.scalar(
            select(SupportCaseRecord).where(SupportCaseRecord.id == case_id).with_for_update()
        )
        if case is None:
            return None
        revision = await self.session.scalar(
            select(SupportRevisionRecord)
            .where(SupportRevisionRecord.case_id == case_id)
            .order_by(SupportRevisionRecord.version.desc())
            .limit(1)
        )
        if revision is None:
            raise RuntimeError("Support case lost its recorded revision")
        return OperatorSupportCase(
            receipt(case, revision),
            case.actor_id,
            SupportContent(
                SupportTopic(case.topic), case.reply_address, case.message, case.details
            ),
        )

    async def status_intent(self, operator_id: UUID, key: IntentKey) -> SupportIntent | None:
        # Serialize same operator key across sessions and different target cases.
        lock = int.from_bytes(operator_id.bytes[:8], "big", signed=True)
        await self.session.execute(select(func.pg_advisory_xact_lock(lock)))
        record = await self.session.get(SupportOperatorIntentRecord, (operator_id, key.value))
        if record is None:
            return None
        case = await self.session.get(SupportCaseRecord, record.case_id)
        revision = await self.session.get(
            SupportRevisionRecord, (record.case_id, record.result_version)
        )
        if case is None or revision is None:
            raise RuntimeError("Support status replay lost its source")
        return SupportIntent(record.fingerprint, receipt(case, revision))

    async def save_status(self, access: OperatorAccess, receipt: SupportReceipt) -> None:
        if access != self.checked_access():
            raise RuntimeError("Support mutation requires actual locked operator grant")
        self.session.add(
            SupportRevisionRecord(
                case_id=receipt.case_id,
                version=receipt.version,
                status=receipt.status.value,
                changed_at=receipt.changed_at,
                changed_by_id=access.account_id,
                operator_access_version=access.version,
            )
        )
        await self.session.flush()
        await self.record_event(self.session, access.account_id, receipt)

    async def remember_status(
        self, operator_id: UUID, key: IntentKey, intent: SupportIntent, at: datetime
    ) -> None:
        self.session.add(
            SupportOperatorIntentRecord(
                operator_id=operator_id,
                key=key.value,
                fingerprint=intent.fingerprint,
                case_id=intent.receipt.case_id,
                result_version=intent.receipt.version,
                created_at=at,
            )
        )
        await self.session.flush()


@dataclass(frozen=True, slots=True)
class SqlOperatorSupportUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    record_event: SupportEventRecorder
    record_audit: OperatorAuditRecorder

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlOperatorSupportTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlOperatorSupportTransaction(
                session, self.record_audit, record_event=self.record_event
            )
