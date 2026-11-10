from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.support.cases import (
    PROOF_LIMIT,
    RECENT_RECEIPT_LIMIT,
    SOURCE_LIMIT,
    SOURCE_WINDOW,
    NewSupportCase,
    SupportIntent,
    SupportProof,
    SupportQuotaError,
)
from studymate.domain.support.cases import SupportReceipt, SupportStatus
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.transactions import open_transaction
from studymate.infrastructure.support.models import (
    SupportCaseRecord,
    SupportIntentRecord,
    SupportPreparationRecord,
    SupportProofRecord,
    SupportRevisionRecord,
)

PREPARATION_LIMIT = 10


class SupportEventRecorder(Protocol):
    async def __call__(
        self, session: AsyncSession, actor_id: UUID | None, receipt: SupportReceipt
    ) -> None:
        """Record only real actor-linked canonical events; never invent anonymous identity."""
        ...


def receipt(case: SupportCaseRecord, revision: SupportRevisionRecord) -> SupportReceipt:
    return SupportReceipt(
        case.id,
        SupportStatus(revision.status),
        revision.version,
        case.received_at,
        revision.changed_at,
    )


@dataclass(frozen=True, slots=True)
class SqlSupportTransaction(SqlIdentityTransaction):
    record_event: SupportEventRecorder

    async def lock_proof(self, digest: bytes) -> SupportProof | None:
        record = await self.session.scalar(
            select(SupportProofRecord).where(SupportProofRecord.digest == digest).with_for_update()
        )
        if record is None:
            return None
        return SupportProof(
            record.digest, record.source_digest, record.created_at, record.expires_at
        )

    async def create_proof(self, proof: SupportProof) -> None:
        self.session.add(
            SupportProofRecord(
                digest=proof.digest,
                source_digest=proof.source_digest,
                created_at=proof.created_at,
                expires_at=proof.expires_at,
            )
        )
        await self.session.flush()

    async def _lock_source(self, source_digest: bytes) -> None:
        # Same source lock for preparation and submission. No user-supplied lock key.
        lock_key = int.from_bytes(source_digest[:8], "big", signed=True)
        await self.session.execute(select(func.pg_advisory_xact_lock(lock_key)))

    async def admit_preparation(self, source_digest: bytes, at: datetime) -> None:
        await self._lock_source(source_digest)
        now = max(at, await self.now())
        count = await self.session.scalar(
            select(func.count())
            .select_from(SupportPreparationRecord)
            .where(
                SupportPreparationRecord.source_digest == source_digest,
                SupportPreparationRecord.created_at > now - timedelta(hours=1),
            )
        )
        if count is None or count >= PREPARATION_LIMIT:
            raise SupportQuotaError
        self.session.add(
            SupportPreparationRecord(id=uuid4(), source_digest=source_digest, created_at=now)
        )
        await self.session.flush()

    async def admit_case(self, proof: SupportProof, at: datetime) -> None:
        await self._lock_source(proof.source_digest)
        now = max(at, await self.now())
        by_source = await self.session.scalar(
            select(func.count())
            .select_from(SupportCaseRecord)
            .join(SupportProofRecord, SupportCaseRecord.proof_digest == SupportProofRecord.digest)
            .where(
                SupportProofRecord.source_digest == proof.source_digest,
                SupportCaseRecord.received_at > now - SOURCE_WINDOW,
            )
        )
        by_proof = await self.session.scalar(
            select(func.count())
            .select_from(SupportCaseRecord)
            .where(SupportCaseRecord.proof_digest == proof.digest)
        )
        if (
            by_source is None
            or by_proof is None
            or by_source >= SOURCE_LIMIT
            or by_proof >= PROOF_LIMIT
        ):
            raise SupportQuotaError

    async def intent(self, digest: bytes, key: IntentKey) -> SupportIntent | None:
        record = await self.session.get(SupportIntentRecord, (digest, key.value))
        if record is None:
            return None
        case = await self.session.get(SupportCaseRecord, record.case_id)
        revision = await self.session.get(
            SupportRevisionRecord, (record.case_id, record.result_version)
        )
        if case is None or revision is None:
            raise RuntimeError("Support replay lost its actual immutable source")
        return SupportIntent(record.fingerprint, receipt(case, revision))

    async def create_case(self, case: NewSupportCase) -> None:
        proof, actor_id, content = case.proof, case.actor_id, case.content
        receipt, key, fingerprint = case.receipt, case.key, case.fingerprint
        self.session.add(
            SupportCaseRecord(
                id=receipt.case_id,
                proof_digest=proof.digest,
                actor_id=actor_id,
                topic=content.topic.value,
                reply_address=content.reply_address,
                message=content.message,
                details=content.details,
                received_at=receipt.received_at,
            )
        )
        await self.session.flush()
        self.session.add(
            SupportRevisionRecord(
                case_id=receipt.case_id,
                version=1,
                status=receipt.status.value,
                changed_at=receipt.changed_at,
            )
        )
        await self.session.flush()
        self.session.add(
            SupportIntentRecord(
                proof_digest=proof.digest,
                key=key.value,
                fingerprint=fingerprint,
                case_id=receipt.case_id,
                result_version=1,
                created_at=receipt.received_at,
            )
        )
        await self.session.flush()
        await self.record_event(self.session, actor_id, receipt)

    async def owned_receipt(self, digest: bytes, case_id: UUID) -> SupportReceipt | None:
        case = await self.session.scalar(
            select(SupportCaseRecord).where(
                SupportCaseRecord.id == case_id, SupportCaseRecord.proof_digest == digest
            )
        )
        return await self._receipt(case)

    async def actor_receipt(self, actor_id: UUID, case_id: UUID) -> SupportReceipt | None:
        case = await self.session.scalar(
            select(SupportCaseRecord).where(
                SupportCaseRecord.id == case_id, SupportCaseRecord.actor_id == actor_id
            )
        )
        return await self._receipt(case)

    async def proof_receipts(self, digest: bytes) -> tuple[SupportReceipt, ...]:
        return await self._recent_receipts(proof_digest=digest)

    async def actor_receipts(self, actor_id: UUID) -> tuple[SupportReceipt, ...]:
        return await self._recent_receipts(actor_id=actor_id)

    async def _recent_receipts(
        self,
        *,
        proof_digest: bytes | None = None,
        actor_id: UUID | None = None,
    ) -> tuple[SupportReceipt, ...]:
        # Ownership filters are applied before the bounded recent projection.
        latest = (
            select(SupportRevisionRecord.version)
            .where(SupportRevisionRecord.case_id == SupportCaseRecord.id)
            .order_by(SupportRevisionRecord.version.desc())
            .limit(1)
            .correlate(SupportCaseRecord)
            .scalar_subquery()
        )
        statement = select(SupportCaseRecord, SupportRevisionRecord).join(
            SupportRevisionRecord,
            (SupportRevisionRecord.case_id == SupportCaseRecord.id)
            & (SupportRevisionRecord.version == latest),
        )
        if proof_digest is not None:
            statement = statement.where(SupportCaseRecord.proof_digest == proof_digest)
        elif actor_id is not None:
            statement = statement.where(SupportCaseRecord.actor_id == actor_id)
        else:
            raise RuntimeError("Recent support receipts require proven ownership")
        rows = (
            await self.session.execute(
                statement.order_by(
                    SupportCaseRecord.received_at.desc(), SupportCaseRecord.id.desc()
                ).limit(RECENT_RECEIPT_LIMIT)
            )
        ).all()
        return tuple(receipt(case, revision) for case, revision in rows)

    async def _receipt(self, case: SupportCaseRecord | None) -> SupportReceipt | None:
        if case is None:
            return None
        revision = await self.session.scalar(
            select(SupportRevisionRecord)
            .where(SupportRevisionRecord.case_id == case.id)
            .order_by(SupportRevisionRecord.version.desc())
            .limit(1)
        )
        if revision is None:
            raise RuntimeError("Support case has no actual status revision")
        return receipt(case, revision)


@dataclass(frozen=True, slots=True)
class SqlSupportUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    record_event: SupportEventRecorder

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlSupportTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlSupportTransaction(session, self.record_event)
