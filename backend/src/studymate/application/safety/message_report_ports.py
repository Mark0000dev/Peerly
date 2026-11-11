"""Actual accepted-message evidence and the existing unified report transaction."""

from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Protocol
from uuid import UUID

from studymate.application.idempotency import IntentKey
from studymate.application.messaging.ports import ConversationAuthority
from studymate.application.safety.profile_reports import ReportBudget, ReportIntent
from studymate.domain.message_reports import (
    MessageImageReport,
    MessageImageReportContext,
    ReportMessageSource,
)


class MessageReportTransaction(ConversationAuthority, Protocol):
    async def message_source(
        self, actor_id: UUID, conversation_id: UUID, message_id: UUID
    ) -> ReportMessageSource | None: ...

    async def owned_context(
        self, actor_id: UUID, context_id: UUID
    ) -> MessageImageReportContext | None: ...

    async def add_context(self, context: MessageImageReportContext) -> None: ...

    async def report_intent(self, actor_id: UUID, key: IntentKey) -> ReportIntent | None: ...

    async def own_message_report(
        self, actor_id: UUID, report_id: UUID
    ) -> MessageImageReport | None: ...

    async def report_budget(self, actor_id: UUID, since: datetime) -> ReportBudget: ...

    async def add_message_report(self, report: MessageImageReport) -> None:
        """Same report root/journal/canonical family; no private content in events."""
        ...

    async def remember_report_intent(
        self, actor_id: UUID, key: IntentKey, intent: ReportIntent, at: datetime
    ) -> None: ...


class MessageReportUnitOfWork(Protocol):
    def for_message(
        self, conversation_id: UUID
    ) -> AbstractAsyncContextManager[MessageReportTransaction]: ...

    def for_context(
        self, context_id: UUID
    ) -> AbstractAsyncContextManager[MessageReportTransaction]:
        """Resolve actual conversation for sorted account locks BEFORE original session.

        The opaque context lookup supplies lock scope only, never report/read authority.
        Missing context does not invent a conversation or bypass live identity checks.
        """
        ...
