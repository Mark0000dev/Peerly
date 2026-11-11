from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.profiles.visibility import VisibilityIntent
from studymate.domain.discovery_freshness import ExposureConfirmation
from studymate.domain.onboarding import ProfileLifecycle
from studymate.infrastructure.persistence.discovery_exposure import (
    confirm_discovery_exposure,
    record_foreground_activity,
)
from studymate.infrastructure.persistence.onboarding import SqlProfileSetupTransaction
from studymate.infrastructure.persistence.onboarding_models import (
    ProfileActivationRecord,
    VisibilityIntentRecord,
    VisibilityRevisionRecord,
)
from studymate.infrastructure.persistence.product_events import (
    record_exposure_confirmation_event,
    record_request_outcome,
    record_visibility_event,
)
from studymate.infrastructure.persistence.transactions import open_transaction
from studymate.infrastructure.requests.lifecycle import close_actor_requests


@dataclass(frozen=True, slots=True)
class SqlVisibilityTransaction(SqlProfileSetupTransaction):
    async def visibility_revision(self, account_id: UUID, version: int) -> ProfileLifecycle:
        record = await self.session.get(VisibilityRevisionRecord, (account_id, version))
        if record is None:
            raise RuntimeError("Saved visibility result is unavailable")
        return ProfileLifecycle(
            account_id, record.completed_at, record.version, record.hidden_at, record.changed_at
        )

    async def visibility_intent(self, account_id: UUID, key: IntentKey) -> VisibilityIntent | None:
        record = await self.session.get(VisibilityIntentRecord, (account_id, key.value))
        if record is None:
            return None
        confirmation = None
        if record.confirmed_exposure_at is not None:
            if record.previous_exposure_paused_at is None:
                raise RuntimeError("Saved exposure confirmation is incomplete")
            confirmation = ExposureConfirmation(
                account_id, record.confirmed_exposure_at, record.previous_exposure_paused_at
            )
        return VisibilityIntent(record.fingerprint, record.result_version, confirmation)

    async def confirm_discovery_exposure(
        self,
        account_id: UUID,
        key: IntentKey,
        at: datetime,
    ) -> ExposureConfirmation | None:
        return await confirm_discovery_exposure(self.session, account_id, key, at)

    async def save_visibility(self, lifecycle: ProfileLifecycle) -> None:
        self.session.add(
            VisibilityRevisionRecord(
                account_id=lifecycle.account_id,
                version=lifecycle.visibility_version,
                completed_at=lifecycle.completed_at,
                hidden_at=lifecycle.hidden_at,
                changed_at=lifecycle.changed_at,
            )
        )
        await self.session.flush()
        await self.session.execute(
            update(ProfileActivationRecord)
            .where(ProfileActivationRecord.account_id == lifecycle.account_id)
            .values(visibility_version=lifecycle.visibility_version)
        )

        await record_visibility_event(self.session, lifecycle)
        if lifecycle.hidden_at is not None:
            await close_actor_requests(
                self.session, lifecycle.account_id, lifecycle.account_id, record_request_outcome
            )

    async def remember_visibility_intent(
        self, account_id: UUID, key: IntentKey, intent: VisibilityIntent, at: datetime
    ) -> None:
        self.session.add(
            VisibilityIntentRecord(
                account_id=account_id,
                key=key.value,
                fingerprint=intent.fingerprint,
                result_version=intent.result_version,
                created_at=at,
                confirmed_exposure_at=intent.exposure_confirmation.confirmed_at
                if intent.exposure_confirmation is not None
                else None,
                previous_exposure_paused_at=intent.exposure_confirmation.previous_paused_at
                if intent.exposure_confirmation is not None
                else None,
            )
        )
        await self.session.flush()
        if intent.exposure_confirmation is not None:
            await record_exposure_confirmation_event(
                self.session, intent.exposure_confirmation, intent.result_version
            )
        else:
            await record_foreground_activity(self.session, account_id, at)


@dataclass(frozen=True, slots=True)
class SqlVisibilityUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlVisibilityTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlVisibilityTransaction(session)
