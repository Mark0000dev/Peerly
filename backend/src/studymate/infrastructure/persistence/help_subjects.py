from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.profiles.help_subjects import (
    HelpIntent,
    HelpTransaction,
    SavedHelpSubjects,
)
from studymate.domain.catalogue import Subject
from studymate.domain.discovery import topic_match_key
from studymate.domain.study_context import HelpRevision, HelpSubject, HelpSubjects
from studymate.infrastructure.persistence.catalogue import SqlSubjectReader
from studymate.infrastructure.persistence.discovery_exposure import record_foreground_activity
from studymate.infrastructure.persistence.help_models import (
    HelpIntentRecord,
    HelpRecord,
    HelpRevisionRecord,
    HelpSelectionRecord,
)
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.product_events import record_help_saved
from studymate.infrastructure.persistence.transactions import open_transaction


@dataclass(frozen=True, slots=True)
class SqlHelpTransaction(SqlIdentityTransaction):
    async def help_subjects(
        self, account_id: UUID, version: int | None = None
    ) -> SavedHelpSubjects | None:
        if version is None:
            root = await self.session.get(HelpRecord, account_id)
            if root is None:
                return None
            version = root.current_version
        record = await self.session.get(HelpRevisionRecord, (account_id, version))
        if record is None:
            return None
        selections = (
            await self.session.scalars(
                select(HelpSelectionRecord)
                .where(
                    HelpSelectionRecord.account_id == account_id,
                    HelpSelectionRecord.version == version,
                )
                .order_by(HelpSelectionRecord.slot)
            )
        ).all()
        return SavedHelpSubjects(
            HelpRevision(
                account_id,
                version,
                HelpSubjects(
                    tuple(HelpSubject(item.subject_id, item.topic_note) for item in selections)
                ),
                record.saved_at,
            ),
            tuple(item.subject_label for item in selections),
        )

    async def help_intent(self, account_id: UUID, key: IntentKey) -> HelpIntent | None:
        record = await self.session.get(HelpIntentRecord, (account_id, key.value))
        return HelpIntent(record.fingerprint, record.result_version) if record is not None else None

    async def subjects(self, subject_ids: tuple[UUID, ...]) -> tuple[Subject, ...]:
        return await SqlSubjectReader(self.session).get_many(subject_ids, lock=True)

    async def save_help(self, value: SavedHelpSubjects) -> None:
        revision = value.revision
        self.session.add(
            HelpRevisionRecord(
                account_id=revision.account_id, version=revision.version, saved_at=revision.saved_at
            )
        )
        await self.session.flush()
        for slot, (item, label) in enumerate(
            zip(revision.subjects.values, value.labels, strict=True)
        ):
            self.session.add(
                HelpSelectionRecord(
                    account_id=revision.account_id,
                    version=revision.version,
                    slot=slot,
                    subject_id=item.subject_id,
                    subject_label=label,
                    topic_note=item.topic_note,
                    topic_match_key=topic_match_key(item.topic_note),
                )
            )
        await self.session.flush()
        if revision.version == 1:
            self.session.add(
                HelpRecord(account_id=revision.account_id, current_version=revision.version)
            )
        else:
            await self.session.execute(
                update(HelpRecord)
                .where(HelpRecord.account_id == revision.account_id)
                .values(current_version=revision.version)
            )
        await self.session.flush()
        await record_help_saved(self.session, revision)

    async def remember_help_intent(
        self, account_id: UUID, key: IntentKey, intent: HelpIntent, at: datetime
    ) -> None:
        self.session.add(
            HelpIntentRecord(
                account_id=account_id,
                key=key.value,
                fingerprint=intent.fingerprint,
                result_version=intent.result_version,
                created_at=at,
            )
        )
        await self.session.flush()
        await record_foreground_activity(self.session, account_id, at)


@dataclass(frozen=True, slots=True)
class SqlHelpUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    shared_identity_locks: bool = False

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[HelpTransaction]:
        async with open_transaction(self.sessions, read_only=self.shared_identity_locks) as session:
            yield SqlHelpTransaction(session, shared_identity_locks=self.shared_identity_locks)
