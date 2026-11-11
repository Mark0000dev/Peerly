from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Self
from uuid import UUID, uuid4

from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import IdentitySnapshot
from studymate.application.messaging.ports import ConversationAccess
from studymate.application.safety.profile_reports import ReportBudget, ReportIntent
from studymate.domain.message_reports import (
    MessageImageRef,
    MessageImageReport,
    MessageImageReportContext,
    ReportMessageSource,
)
from studymate.domain.messaging import ChatConversation
from studymate.domain.relationships import AccountPair
from tests.unit.identity_store import NOW, IdentityStore


class Store(IdentityStore):
    def __init__(self) -> None:
        super().__init__()
        self.actor = replace(self.actor, activation_complete=True)
        pair = AccountPair.between(self.actor.session.account_id, UUID(int=3))
        self.access: ConversationAccess | None = ConversationAccess(
            ChatConversation(uuid4(), uuid4(), pair, uuid4(), 2, 1), True, False, False, False
        )
        self.source: ReportMessageSource | None = ReportMessageSource(
            uuid4(),
            self.access.conversation.id,
            pair,
            UUID(int=3),
            uuid4(),
            NOW - timedelta(minutes=1),
            MessageImageRef(uuid4(), 3, uuid4()),
        )
        self.contexts: dict[UUID, MessageImageReportContext] = {}
        self.reports: dict[UUID, MessageImageReport] = {}
        self.intents: dict[IntentKey, ReportIntent] = {}
        self.profile_submissions: tuple[datetime, ...] = ()
        self.events: list[UUID] = []
        self.budget_reads = 0
        self.expire_after_context = False
        self.expire_after_intent = False
        self.failure_after_report = False
        self.bad_context = False
        self.switch_session = False
        self.identity_reads = 0

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Self]:
        before = self.contexts.copy(), self.reports.copy(), self.intents.copy(), self.events.copy()
        try:
            yield self
        except BaseException:
            self.contexts, self.reports, self.intents, self.events = before
            raise

    def for_message(self, conversation_id: UUID) -> AbstractAsyncContextManager[Self]:
        assert self.source is None or conversation_id == self.source.conversation_id
        return self.transaction()

    def for_context(self, context_id: UUID) -> AbstractAsyncContextManager[Self]:
        del context_id
        return self.transaction()

    async def lock_identity(self, secret_digest: bytes) -> IdentitySnapshot:
        identity = await super().lock_identity(secret_digest)
        assert identity is not None
        self.identity_reads += 1
        if self.switch_session and self.identity_reads > 1:
            return replace(identity, session=replace(identity.session, id=uuid4()))
        return identity

    async def conversation(
        self, actor_id: UUID, conversation_id: UUID
    ) -> ConversationAccess | None:
        assert actor_id == self.actor.session.account_id
        assert self.access is None or self.access.conversation.id == conversation_id
        return self.access

    async def message_source(
        self, actor_id: UUID, conversation_id: UUID, message_id: UUID
    ) -> ReportMessageSource | None:
        assert actor_id == self.actor.session.account_id
        del conversation_id, message_id
        return self.source

    async def owned_context(
        self, actor_id: UUID, context_id: UUID
    ) -> MessageImageReportContext | None:
        context = self.contexts.get(context_id)
        return (
            context
            if context is None or self.bad_context or context.reporter_id == actor_id
            else None
        )

    async def add_context(self, context: MessageImageReportContext) -> None:
        self.contexts[context.id] = context
        if self.expire_after_context:
            self.clock = self.actor.session.expires_at

    async def report_intent(self, actor_id: UUID, key: IntentKey) -> ReportIntent | None:
        assert actor_id == self.actor.session.account_id
        return self.intents.get(key)

    async def own_message_report(
        self, actor_id: UUID, report_id: UUID
    ) -> MessageImageReport | None:
        assert actor_id == self.actor.session.account_id
        return self.reports.get(report_id)

    async def report_budget(self, actor_id: UUID, since: datetime) -> ReportBudget:
        assert actor_id == self.actor.session.account_id
        self.budget_reads += 1
        submissions = tuple(
            at
            for at in (
                *self.profile_submissions,
                *(report.submitted_at for report in self.reports.values()),
            )
            if at >= since
        )
        return ReportBudget(len(submissions), min(submissions) if submissions else None)

    async def add_message_report(self, report: MessageImageReport) -> None:
        self.reports[report.id] = report
        self.events.append(report.id)
        if self.failure_after_report:
            raise RuntimeError("synthetic canonical write failure")

    async def remember_report_intent(
        self, actor_id: UUID, key: IntentKey, intent: ReportIntent, at: datetime
    ) -> None:
        assert actor_id == self.actor.session.account_id
        assert at == self.clock
        self.intents[key] = intent
        if self.expire_after_intent:
            self.clock = self.actor.session.expires_at
