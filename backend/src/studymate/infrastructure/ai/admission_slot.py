"""Request-local lock ownership proof, never a cache of runtime facts or authority."""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    AsyncSessionTransaction,
    AsyncTransaction,
)

from studymate.application.ai.ports import AiUnavailableError
from studymate.infrastructure.ai.models import AiSlotRecord


@dataclass(frozen=True, slots=True)
class HeldAdmissionSlot:
    session: AsyncSession = field(repr=False)
    transaction: AsyncSessionTransaction = field(repr=False)
    savepoint: AsyncSessionTransaction | None = field(repr=False)
    connection: AsyncConnection = field(repr=False)
    connection_root: AsyncTransaction = field(repr=False)
    connection_savepoint: AsyncTransaction | None = field(repr=False)

    def still_held(self, session: AsyncSession) -> bool:
        return (
            session is self.session
            and session.is_active
            and session.get_transaction() is self.transaction
            and self.transaction.is_active
            and session.get_nested_transaction() is self.savepoint
            and (self.savepoint is None or self.savepoint.is_active)
            and not self.connection.closed
            and not self.connection.invalidated
            and self.connection.get_transaction() is self.connection_root
            and self.connection_root.is_active
            and self.connection.get_nested_transaction() is self.connection_savepoint
            and (self.connection_savepoint is None or self.connection_savepoint.is_active)
        )


@dataclass(slots=True)
class AdmissionSlotLock:
    proof: HeldAdmissionSlot | None = field(default=None, repr=False)

    def consume(self, session: AsyncSession) -> bool:
        proof, self.proof = self.proof, None
        return proof is not None and proof.still_held(session)


async def acquire_admission_slot(
    session: AsyncSession,
    remember: AdmissionSlotLock | None = None,
) -> AiSlotRecord:
    # Only the worker creates execution capacity. Missing cannot mean "ready".
    row = await session.scalar(
        select(AiSlotRecord)
        .where(AiSlotRecord.id == 1)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise AiUnavailableError
    if remember is not None:
        transaction = session.get_transaction()
        connection = await session.connection()
        root = connection.get_transaction()
        if transaction is None or root is None:
            raise RuntimeError("Admission slot lock lacks its actual active transaction")
        remember.proof = HeldAdmissionSlot(
            session,
            transaction,
            session.get_nested_transaction(),
            connection,
            root,
            connection.get_nested_transaction(),
        )
    return row


async def ensure_admission_slot(session: AsyncSession, remembered: AdmissionSlotLock) -> None:
    if not remembered.consume(session):
        await acquire_admission_slot(session)
