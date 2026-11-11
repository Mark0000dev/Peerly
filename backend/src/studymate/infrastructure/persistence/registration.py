from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.identity.registration import RegistrationTransaction
from studymate.application.profiles.onboarding import ProfileSetupSnapshot
from studymate.domain.onboarding import OnboardingActivation
from studymate.domain.registration import (
    PolicyKind,
    PolicyReference,
    PolicyVersion,
    PublishedPolicy,
    RegistrationContext,
    RegistrationReceipt,
)
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.onboarding import read_setup_snapshot, record_activation
from studymate.infrastructure.persistence.registration_models import (
    PolicyDocumentRecord,
    RegistrationContextRecord,
    RegistrationReceiptRecord,
)
from studymate.infrastructure.persistence.registration_reads import read_context
from studymate.infrastructure.persistence.transactions import open_transaction


@dataclass(frozen=True, slots=True)
class SqlRegistrationTransaction(SqlIdentityTransaction):
    async def setup_snapshot(self, account_id: UUID) -> ProfileSetupSnapshot:
        return await read_setup_snapshot(self.session, account_id)

    async def activate_profile(self, activation: OnboardingActivation) -> None:
        await record_activation(self.session, activation)

    async def current_reference(self, kind: PolicyKind, at: datetime) -> PolicyReference | None:
        row = (
            await self.session.execute(
                select(
                    PolicyDocumentRecord.id,
                    PolicyDocumentRecord.version,
                    PolicyDocumentRecord.published_at,
                )
                .where(
                    PolicyDocumentRecord.kind == kind.value, PolicyDocumentRecord.published_at <= at
                )
                .order_by(PolicyDocumentRecord.published_at.desc(), PolicyDocumentRecord.id.desc())
                .limit(1)
            )
        ).one_or_none()
        if row is None:
            return None
        identity, version, published_at = row
        return PolicyReference(identity, kind, PolicyVersion(version), published_at)

    async def published_policy(
        self, kind: PolicyKind, version: PolicyVersion | None, at: datetime
    ) -> PublishedPolicy | None:
        statement = select(PolicyDocumentRecord).where(
            PolicyDocumentRecord.kind == kind.value, PolicyDocumentRecord.published_at <= at
        )
        if version is not None:
            statement = statement.where(PolicyDocumentRecord.version == version.value)
        record = (
            await self.session.scalars(
                statement.order_by(
                    PolicyDocumentRecord.published_at.desc(), PolicyDocumentRecord.id.desc()
                ).limit(1)
            )
        ).one_or_none()
        if record is None:
            return None
        return PublishedPolicy(
            PolicyReference(record.id, kind, PolicyVersion(record.version), record.published_at),
            record.title,
            record.content,
        )

    async def context_by_key(self, account_id: UUID, key: IntentKey) -> RegistrationContext | None:
        identity = (
            await self.session.scalars(
                select(RegistrationContextRecord.id).where(
                    RegistrationContextRecord.account_id == account_id,
                    RegistrationContextRecord.intent_key == key.value,
                )
            )
        ).one_or_none()
        return await read_context(self.session, identity) if identity is not None else None

    async def lock_context(self, context_id: UUID) -> RegistrationContext | None:
        return await read_context(self.session, context_id, lock=True)

    async def add_context(self, context: RegistrationContext, key: IntentKey) -> None:
        self.session.add(
            RegistrationContextRecord(
                id=context.id,
                account_id=context.account_id,
                session_id=context.session_id,
                terms_id=context.terms.id,
                privacy_id=context.privacy.id,
                notice_text=context.notice_text,
                surface=context.surface.value,
                intent_key=key.value,
                created_at=context.created_at,
                expires_at=context.expires_at,
                completed_at=context.completed_at,
            )
        )
        await self.session.flush()

    async def record_completion(self, receipt: RegistrationReceipt) -> None:
        await self.session.execute(
            update(RegistrationContextRecord)
            .where(RegistrationContextRecord.id == receipt.context.id)
            .values(completed_at=receipt.registered_at)
        )
        self.session.add(
            RegistrationReceiptRecord(
                id=receipt.id,
                account_id=receipt.account_id,
                context_id=receipt.context.id,
                registered_at=receipt.registered_at,
                intent_key=receipt.intent_key,
            )
        )
        await self.session.flush()


@dataclass(frozen=True, slots=True)
class SqlRegistrationUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[RegistrationTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlRegistrationTransaction(session)
