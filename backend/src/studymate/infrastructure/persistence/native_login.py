"""Native handoff storage; identity locks precede native row locks."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.identity.native_login import (
    NativeAttempt,
    NativeLoginRejectedError,
    NativeTransaction,
)
from studymate.domain.identity import Session
from studymate.infrastructure.persistence.identity_models import SessionRecord
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.native_login_models import (
    NativeAttemptRecord as NativeAttemptRecord,
)
from studymate.infrastructure.persistence.transactions import open_transaction


def _attempt(row: NativeAttemptRecord | None) -> NativeAttempt | None:
    if row is None:
        return None
    return NativeAttempt(
        row.id,
        row.challenge,
        row.browser_digest,
        row.created_at,
        row.expires_at,
        row.source_digest,
        row.consumed_at,
        row.cancelled_at,
    )


@dataclass(frozen=True, slots=True)
class SqlNativeTransaction(SqlIdentityTransaction):
    async def add_native(self, attempt: NativeAttempt) -> None:
        created = await self.session.scalar(
            insert(NativeAttemptRecord)
            .values(
                id=attempt.id,
                challenge=attempt.challenge,
                browser_digest=attempt.browser_digest,
                created_at=attempt.created_at,
                expires_at=attempt.expires_at,
            )
            .on_conflict_do_nothing()
            .returning(NativeAttemptRecord.id)
        )
        if created is None:
            raise NativeLoginRejectedError

    async def native_by_browser(self, digest: bytes) -> NativeAttempt | None:
        return _attempt(
            await self.session.scalar(
                select(NativeAttemptRecord).where(NativeAttemptRecord.browser_digest == digest)
            )
        )

    async def native_by_id(self, attempt_id: UUID) -> NativeAttempt | None:
        return _attempt(await self.session.get(NativeAttemptRecord, attempt_id))

    async def lock_native(self, attempt_id: UUID) -> NativeAttempt | None:
        # Refresh the earlier unlocked lookup after any competing exchange commits.
        return _attempt(
            await self.session.scalar(
                select(NativeAttemptRecord)
                .where(NativeAttemptRecord.id == attempt_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )

    async def bind_native(self, attempt_id: UUID, source_digest: bytes) -> None:
        await self.session.execute(
            update(NativeAttemptRecord)
            .where(NativeAttemptRecord.id == attempt_id)
            .values(source_digest=source_digest)
        )

    async def limit_session_expiry(self, session_id: UUID, expires_at: datetime) -> None:
        await self.session.execute(
            update(SessionRecord)
            .where(SessionRecord.id == session_id, SessionRecord.expires_at > expires_at)
            .values(expires_at=expires_at)
        )

    async def consume_native(self, attempt_id: UUID, at: datetime) -> None:
        await self.session.execute(
            update(NativeAttemptRecord)
            .where(NativeAttemptRecord.id == attempt_id)
            .values(consumed_at=at)
        )

    async def cancel_native(self, attempt_id: UUID, at: datetime) -> None:
        await self.session.execute(
            update(NativeAttemptRecord)
            .where(NativeAttemptRecord.id == attempt_id)
            .values(cancelled_at=at)
        )

    async def add_session(self, session: Session, digest: bytes) -> None:
        self.session.add(
            SessionRecord(
                id=session.id,
                account_id=session.account_id,
                secret_digest=digest,
                issued_at=session.issued_at,
                expires_at=session.expires_at,
            )
        )
        await self.session.flush()


@dataclass(frozen=True, slots=True)
class SqlNativeUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[NativeTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlNativeTransaction(session)
