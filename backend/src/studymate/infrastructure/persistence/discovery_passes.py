from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.discovery.passes import PrivatePassIntent
from studymate.application.idempotency import IntentKey
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.discovery_context import DiscoveryContext
from studymate.domain.discovery_passes import PrivatePassRevision
from studymate.infrastructure.persistence.discovery_decisions import advance_discovery_decision
from studymate.infrastructure.persistence.discovery_exposure import record_foreground_activity
from studymate.infrastructure.persistence.discovery_pass_models import (
    DiscoveryContextRecord,
    DiscoveryDecisionHeadRecord,
    PrivatePassIntentRecord,
    PrivatePassRecord,
    PrivatePassRevisionRecord,
)
from studymate.infrastructure.persistence.discovery_profiles import SqlDiscoveryProfileTransaction
from studymate.infrastructure.persistence.product_events import record_private_pass_event
from studymate.infrastructure.persistence.transactions import open_transaction


def context_value(record: DiscoveryContextRecord) -> DiscoveryContext:
    return DiscoveryContext(
        record.account_id,
        DiscoveryMode(record.mode),
        record.goal_id,
        record.goal_version,
        record.help_version,
    )


@dataclass(frozen=True, slots=True)
class SqlPrivatePassTransaction(SqlDiscoveryProfileTransaction):
    async def _context(self, context: DiscoveryContext) -> DiscoveryContextRecord | None:
        return await self.session.scalar(
            select(DiscoveryContextRecord).where(
                DiscoveryContextRecord.account_id == context.account_id,
                DiscoveryContextRecord.mode == context.mode.value,
                DiscoveryContextRecord.goal_id == context.goal_id,
                DiscoveryContextRecord.goal_version == context.goal_version,
                DiscoveryContextRecord.help_version == context.help_version,
            )
        )

    async def _revision(self, pass_id: UUID, version: int) -> PrivatePassRevision:
        revision = await self.session.get(PrivatePassRevisionRecord, (pass_id, version))
        if revision is None:
            raise RuntimeError("Retained private pass revision is unavailable")
        context = await self.session.get(DiscoveryContextRecord, revision.context_id)
        if context is None:
            raise RuntimeError("Retained private pass context is unavailable")
        return PrivatePassRevision(
            revision.pass_id,
            context_value(context),
            revision.target_id,
            revision.version,
            revision.passed,
            revision.decision_sequence,
            revision.changed_at,
        )

    async def pass_intent(self, actor_id: UUID, key: IntentKey) -> PrivatePassIntent | None:
        intent = await self.session.get(PrivatePassIntentRecord, (actor_id, key.value))
        if intent is None:
            return None
        return PrivatePassIntent(
            intent.fingerprint, await self._revision(intent.pass_id, intent.result_version)
        )

    async def current_pass(
        self, context: DiscoveryContext, target_id: UUID
    ) -> PrivatePassRevision | None:
        saved = await self._context(context)
        if saved is None:
            return None
        root = await self.session.scalar(
            select(PrivatePassRecord).where(
                PrivatePassRecord.context_id == saved.id, PrivatePassRecord.target_id == target_id
            )
        )
        return await self._revision(root.id, root.current_version) if root is not None else None

    async def latest_decision_sequence(self, actor_id: UUID) -> int:
        head = await self.session.get(DiscoveryDecisionHeadRecord, actor_id)
        return head.last_sequence if head is not None else 0

    async def save_pass(self, revision: PrivatePassRevision) -> None:
        context = await self._context(revision.context)
        if context is None:
            source = revision.context
            context = DiscoveryContextRecord(
                id=uuid4(),
                account_id=source.account_id,
                mode=source.mode.value,
                goal_id=source.goal_id,
                goal_version=source.goal_version,
                help_version=source.help_version,
            )
            self.session.add(context)
            await self.session.flush()
        sequence = await advance_discovery_decision(self.session, revision.context.account_id)
        if sequence != revision.decision_sequence:
            raise RuntimeError("Private pass sequence disagrees with the committed decision head")
        root = await self.session.get(PrivatePassRecord, revision.id)
        if root is None:
            if revision.version != 1:
                raise RuntimeError("First private pass revision must be one")
            self.session.add(
                PrivatePassRecord(
                    id=revision.id,
                    account_id=revision.context.account_id,
                    context_id=context.id,
                    target_id=revision.target_id,
                    current_version=revision.version,
                )
            )
            await self.session.flush()
        else:
            if (
                root.context_id != context.id
                or root.target_id != revision.target_id
                or root.account_id != revision.context.account_id
                or root.current_version != revision.version - 1
            ):
                raise RuntimeError("Private pass revision disagrees with its saved source")
            root.current_version = revision.version
        self.session.add(
            PrivatePassRevisionRecord(
                pass_id=revision.id,
                version=revision.version,
                account_id=revision.context.account_id,
                context_id=context.id,
                target_id=revision.target_id,
                passed=revision.passed,
                decision_sequence=revision.decision_sequence,
                changed_at=revision.changed_at,
            )
        )
        await self.session.flush()

        await record_private_pass_event(self.session, revision)

    async def remember_pass_intent(
        self, actor_id: UUID, key: IntentKey, intent: PrivatePassIntent, at: datetime
    ) -> None:
        self.session.add(
            PrivatePassIntentRecord(
                account_id=actor_id,
                key=key.value,
                fingerprint=intent.fingerprint,
                pass_id=intent.result.id,
                result_version=intent.result.version,
                created_at=at,
            )
        )
        await self.session.flush()
        await record_foreground_activity(self.session, actor_id, at)


@dataclass(frozen=True, slots=True)
class SqlPrivatePassUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self, target_id: UUID) -> AsyncIterator[SqlPrivatePassTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlPrivatePassTransaction(session, target_id)
