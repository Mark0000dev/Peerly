from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.notification_preferences.preferences import PreferenceIntent
from studymate.domain.notification_preferences.state import NotificationMode, NotificationPreference
from studymate.infrastructure.notification_preferences.models import (
    PreferenceIntentRecord,
    PreferenceRevisionRecord,
)
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.transactions import open_transaction


class PreferenceEventRecorder(Protocol):
    async def __call__(
        self, session: AsyncSession, account_id: UUID, result: NotificationPreference
    ) -> None: ...


def preference(record: PreferenceRevisionRecord) -> NotificationPreference:
    return NotificationPreference(NotificationMode(record.mode), record.version, record.changed_at)


@dataclass(frozen=True, slots=True)
class SqlPreferenceTransaction(SqlIdentityTransaction):
    record_event: PreferenceEventRecorder

    async def preference(self, account_id: UUID) -> NotificationPreference:
        record = await self.session.scalar(
            select(PreferenceRevisionRecord)
            .where(PreferenceRevisionRecord.account_id == account_id)
            .order_by(PreferenceRevisionRecord.version.desc())
            .limit(1)
        )
        return preference(record) if record is not None else NotificationPreference()

    async def intent(self, account_id: UUID, key: IntentKey) -> PreferenceIntent | None:
        record = await self.session.get(PreferenceIntentRecord, (account_id, key.value))
        if record is None:
            return None
        result = NotificationPreference()
        if record.result_version is not None:
            revision = await self.session.get(
                PreferenceRevisionRecord, (account_id, record.result_version)
            )
            if revision is None:
                raise RuntimeError("Preference replay lost its immutable revision")
            result = preference(revision)
        return PreferenceIntent(record.fingerprint, result)

    async def save(self, account_id: UUID, result: NotificationPreference) -> None:
        self.session.add(
            PreferenceRevisionRecord(
                account_id=account_id,
                version=result.version,
                mode=result.mode.value,
                changed_at=result.changed_at,
            )
        )
        await self.session.flush()
        await self.record_event(self.session, account_id, result)

    async def remember(
        self, account_id: UUID, key: IntentKey, intent: PreferenceIntent, at: datetime
    ) -> None:
        self.session.add(
            PreferenceIntentRecord(
                account_id=account_id,
                key=key.value,
                fingerprint=intent.fingerprint,
                result_version=intent.result.version or None,
                created_at=at,
            )
        )
        await self.session.flush()


@dataclass(frozen=True, slots=True)
class SqlPreferenceUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    record_event: PreferenceEventRecorder
    shared_identity_locks: bool = False

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlPreferenceTransaction]:
        async with open_transaction(self.sessions, read_only=self.shared_identity_locks) as session:
            yield SqlPreferenceTransaction(
                session, self.record_event, shared_identity_locks=self.shared_identity_locks
            )
