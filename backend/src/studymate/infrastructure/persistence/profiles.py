from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.profiles.basics import ProfileIntent
from studymate.domain.media import PhotoRevision
from studymate.domain.profiles import (
    DisplayName,
    LanguageCode,
    OnboardingTask,
    ProfileBasics,
    ProfileRevision,
)
from studymate.infrastructure.persistence.discovery_exposure import record_foreground_activity
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.media_uploads import SqlMediaTransaction
from studymate.infrastructure.persistence.product_events import record_profile_saved
from studymate.infrastructure.persistence.profile_models import (
    ProfileIntentRecord,
    ProfileLanguageRecord,
    ProfileRecord,
    ProfileRevisionRecord,
)
from studymate.infrastructure.persistence.transactions import open_transaction


@dataclass(frozen=True, slots=True)
class SqlProfileTransaction(SqlIdentityTransaction):
    async def current_photo(self, account_id: UUID) -> PhotoRevision | None:
        return await SqlMediaTransaction(self.session).current_photo(account_id)

    async def profile(self, account_id: UUID, version: int | None = None) -> ProfileRevision | None:
        if version is None:
            version = (
                await self.session.scalars(
                    select(ProfileRecord.current_version).where(
                        ProfileRecord.account_id == account_id
                    )
                )
            ).one_or_none()
            if version is None:
                return None
        record = await self.session.get(ProfileRevisionRecord, (account_id, version))
        if record is None:
            return None
        languages = tuple(
            LanguageCode(code)
            for code in await self.session.scalars(
                select(ProfileLanguageRecord.code)
                .where(
                    ProfileLanguageRecord.account_id == account_id,
                    ProfileLanguageRecord.version == version,
                )
                .order_by(ProfileLanguageRecord.slot)
            )
        )
        return ProfileRevision(
            account_id,
            record.version,
            ProfileBasics(
                DisplayName(record.display_name) if record.display_name is not None else None,
                record.about,
                record.programme,
                record.year_label,
                languages,
            ),
            OnboardingTask(record.task),
            record.saved_at,
        )

    async def profile_intent(self, account_id: UUID, key: IntentKey) -> ProfileIntent | None:
        record = await self.session.get(ProfileIntentRecord, (account_id, key.value))
        return (
            ProfileIntent(record.fingerprint, record.result_version) if record is not None else None
        )

    async def save_profile(self, revision: ProfileRevision) -> None:
        basics = revision.basics
        self.session.add(
            ProfileRevisionRecord(
                account_id=revision.account_id,
                version=revision.version,
                display_name=basics.display_name.value if basics.display_name is not None else None,
                about=basics.about,
                programme=basics.programme,
                year_label=basics.year_label,
                task=revision.task.value,
                saved_at=revision.saved_at,
            )
        )
        await self.session.flush()
        self.session.add_all(
            ProfileLanguageRecord(
                account_id=revision.account_id,
                version=revision.version,
                slot=slot,
                code=language.value,
            )
            for slot, language in enumerate(basics.languages)
        )
        if revision.version == 1:
            self.session.add(
                ProfileRecord(account_id=revision.account_id, current_version=revision.version)
            )
        else:
            await self.session.execute(
                update(ProfileRecord)
                .where(ProfileRecord.account_id == revision.account_id)
                .values(current_version=revision.version)
            )
        await self.session.flush()
        await record_profile_saved(self.session, revision)

    async def remember_profile_intent(
        self, account_id: UUID, key: IntentKey, intent: ProfileIntent, at: datetime
    ) -> None:
        self.session.add(
            ProfileIntentRecord(
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
class SqlProfileUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlProfileTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlProfileTransaction(session)
