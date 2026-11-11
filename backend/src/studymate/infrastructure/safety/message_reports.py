"""Participant image evidence in the existing report root, intents and quota journal."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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
from studymate.domain.relationships import AccountPair
from studymate.domain.reports import ReportCategory
from studymate.infrastructure.observability.tracing import current_origin
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.message_models import MessageRecord
from studymate.infrastructure.persistence.message_report_models import MessageReportContextRecord
from studymate.infrastructure.persistence.messaging import SqlMessageTransaction
from studymate.infrastructure.persistence.product_events import record_message_outcome
from studymate.infrastructure.persistence.profile_reports import SqlProfileReportTransaction
from studymate.infrastructure.persistence.report_models import ProfileReportRecord
from studymate.infrastructure.persistence.transactions import open_transaction


class MessageReportEventRecorder(Protocol):
    async def __call__(self, session: AsyncSession, report: MessageImageReport) -> None:
        """Append actual existing report.created in this transaction, never commit/network."""
        ...


def context_value(row: MessageReportContextRecord, sent_at: datetime) -> MessageImageReportContext:
    return MessageImageReportContext(
        row.id,
        row.viewer_id,
        ReportMessageSource(
            row.message_id,
            row.conversation_id,
            AccountPair(row.low_id, row.high_id),
            row.target_id,
            row.client_message_id,
            sent_at,
            MessageImageRef(row.image_id, row.image_version, row.image_attempt_id),
        ),
        row.issued_at,
    )


@dataclass(slots=True)
class MessageReportAuthority:
    resolved: bool = False
    actor_id: UUID | None = None
    delegate: SqlMessageTransaction | None = None
    access: ConversationAccess | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class SqlMessageReportTransaction(SqlIdentityTransaction):
    recorder: MessageReportEventRecorder
    requested_conversation_id: UUID | None
    context_id: UUID | None
    authority: MessageReportAuthority = field(default_factory=MessageReportAuthority)

    async def lock_identity(self, secret_digest: bytes) -> IdentitySnapshot | None:
        if not self.authority.resolved:
            conversation_id = self.requested_conversation_id
            if conversation_id is None and self.context_id is not None:
                # Lock scope only. Exact current actor/context ownership is checked
                # after the common identity guard; the UUID never grants authority.
                conversation_id = await self.session.scalar(
                    select(MessageReportContextRecord.conversation_id).where(
                        MessageReportContextRecord.id == self.context_id
                    )
                )
            if conversation_id is not None:
                self.authority.delegate = SqlMessageTransaction(
                    self.session, conversation_id, record_message_outcome
                )
            self.authority.resolved = True
        delegate = self.authority.delegate
        return (
            await delegate.lock_identity(secret_digest)
            if delegate is not None
            else await SqlIdentityTransaction.lock_identity(self, secret_digest)
        )

    def authenticated(self, account_id: UUID) -> None:
        self.authority.actor_id = account_id
        delegate = self.authority.delegate
        if delegate is not None:
            delegate.authenticated(account_id)
        else:
            SqlIdentityTransaction.authenticated(self, account_id)

    def check_actor(self, actor_id: UUID) -> None:
        if self.authority.actor_id != actor_id:
            raise RuntimeError("Message report lacks actual current actor authority")

    def check_conversation(self, actor_id: UUID, conversation_id: UUID) -> ConversationAccess:
        self.check_actor(actor_id)
        access = self.authority.access
        if access is None or access.conversation.id != conversation_id:
            raise RuntimeError("Message report lacks actual accepted conversation authority")
        return access

    async def conversation(
        self, actor_id: UUID, conversation_id: UUID
    ) -> ConversationAccess | None:
        self.check_actor(actor_id)
        delegate = self.authority.delegate
        if delegate is None or delegate.conversation_id != conversation_id:
            raise RuntimeError("Message report conversation differs from its resolved lock scope")
        access = await delegate.conversation(actor_id, conversation_id)
        self.authority.access = access
        return access

    async def message_source(
        self, actor_id: UUID, conversation_id: UUID, message_id: UUID
    ) -> ReportMessageSource | None:
        self.check_conversation(actor_id, conversation_id)
        message = MessageRecord
        # Immutable identifiers/timestamp only: never project private message text.
        row = (
            await self.session.execute(
                select(
                    message.id,
                    message.conversation_id,
                    message.low_id,
                    message.high_id,
                    message.author_id,
                    message.client_message_id,
                    message.sent_at,
                    message.image_id,
                    message.image_version,
                    message.image_attempt_id,
                ).where(message.id == message_id, message.conversation_id == conversation_id)
            )
        ).one_or_none()
        if row is None:
            return None
        image_id, version, attempt_id = row.image_id, row.image_version, row.image_attempt_id
        image = None
        if image_id is not None and version is not None and attempt_id is not None:
            image = MessageImageRef(image_id, version, attempt_id)
        elif image_id is not None or version is not None or attempt_id is not None:
            raise RuntimeError("Message report source lost its actual all-or-none image FK")
        return ReportMessageSource(
            row.id,
            row.conversation_id,
            AccountPair(row.low_id, row.high_id),
            row.author_id,
            row.client_message_id,
            row.sent_at,
            image,
        )

    async def owned_context(
        self, actor_id: UUID, context_id: UUID
    ) -> MessageImageReportContext | None:
        self.check_actor(actor_id)
        context = MessageReportContextRecord
        row = (
            await self.session.execute(
                select(context, MessageRecord.sent_at)
                .join(MessageRecord, MessageRecord.id == context.message_id)
                .where(context.id == context_id, context.viewer_id == actor_id)
            )
        ).one_or_none()
        if row is None:
            return None
        stored, sent_at = row
        delegate = self.authority.delegate
        if delegate is None or stored.conversation_id != delegate.conversation_id:
            raise RuntimeError("Message context differs from its actual conversation lock scope")
        return context_value(stored, sent_at)

    async def add_context(self, context: MessageImageReportContext) -> None:
        source = context.source
        self.check_conversation(context.reporter_id, source.conversation_id)
        actual = await self.message_source(
            context.reporter_id, source.conversation_id, source.message_id
        )
        if actual != source or source.image is None:
            raise RuntimeError("Message context differs from actual confirmed image evidence")
        origin = current_origin()
        self.session.add(
            MessageReportContextRecord(
                id=context.id,
                viewer_id=context.reporter_id,
                message_id=source.message_id,
                conversation_id=source.conversation_id,
                low_id=source.pair.low,
                high_id=source.pair.high,
                target_id=source.author_id,
                client_message_id=source.client_message_id,
                image_id=source.image.id,
                image_version=source.image.version,
                image_attempt_id=source.image.attempt_id,
                image_state="ready",
                issued_at=context.issued_at,
                request_id=origin.request_id if origin is not None else None,
                action_id=origin.action_id if origin is not None else None,
                trace_id=origin.trace_id if origin is not None else None,
                span_id=origin.span_id if origin is not None else None,
            )
        )
        await self.session.flush()

    async def report_intent(self, actor_id: UUID, key: IntentKey) -> ReportIntent | None:
        self.check_actor(actor_id)
        return await SqlProfileReportTransaction(self.session).report_intent(actor_id, key)

    async def own_message_report(
        self, actor_id: UUID, report_id: UUID
    ) -> MessageImageReport | None:
        self.check_actor(actor_id)
        report, context = ProfileReportRecord, MessageReportContextRecord
        row = (
            await self.session.execute(
                select(report, context, MessageRecord.sent_at)
                .join(
                    context,
                    and_(
                        context.id == report.message_context_id,
                        context.viewer_id == report.reporter_id,
                    ),
                )
                .join(MessageRecord, MessageRecord.id == context.message_id)
                .where(
                    report.id == report_id,
                    report.reporter_id == actor_id,
                    report.kind == "message_image",
                )
            )
        ).one_or_none()
        if row is None:
            return None
        stored, source, sent_at = row
        return MessageImageReport(
            stored.id,
            stored.reporter_id,
            context_value(source, sent_at),
            ReportCategory(stored.category),
            stored.submitted_at,
            stored.comment,
        )

    async def report_budget(self, actor_id: UUID, since: datetime) -> ReportBudget:
        self.check_actor(actor_id)
        return await SqlProfileReportTransaction(self.session).report_budget(actor_id, since)

    async def add_message_report(self, report: MessageImageReport) -> None:
        self.check_conversation(report.reporter_id, report.context.source.conversation_id)
        if await self.owned_context(report.reporter_id, report.context.id) != report.context:
            raise RuntimeError("Report write lost its actual retained owned image context")
        self.session.add(
            ProfileReportRecord(
                id=report.id,
                reporter_id=report.reporter_id,
                kind="message_image",
                context_id=None,
                message_context_id=report.context.id,
                category=report.category.value,
                comment=report.comment,
                submitted_at=report.submitted_at,
            )
        )
        await self.session.flush()
        await self.recorder(self.session, report)

    async def remember_report_intent(
        self, actor_id: UUID, key: IntentKey, intent: ReportIntent, at: datetime
    ) -> None:
        self.check_actor(actor_id)
        await SqlProfileReportTransaction(self.session).remember_report_intent(
            actor_id, key, intent, at
        )


@dataclass(frozen=True, slots=True)
class SqlMessageReportUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: MessageReportEventRecorder

    @asynccontextmanager
    async def for_message(
        self, conversation_id: UUID
    ) -> AsyncIterator[SqlMessageReportTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlMessageReportTransaction(
                session,
                recorder=self.recorder,
                requested_conversation_id=conversation_id,
                context_id=None,
            )

    @asynccontextmanager
    async def for_context(self, context_id: UUID) -> AsyncIterator[SqlMessageReportTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlMessageReportTransaction(
                session,
                recorder=self.recorder,
                requested_conversation_id=None,
                context_id=context_id,
            )
