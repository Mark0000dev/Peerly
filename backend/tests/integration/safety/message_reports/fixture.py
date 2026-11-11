"""Actual accepted image message and participant report adapters; no live storage/provider."""

from dataclasses import dataclass, replace

from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.idempotency import IntentKey
from studymate.application.safety.message_reports import (
    IssueMessageImageReportContext,
    SubmitMessageImageReport,
    SubmitMessageImageReportCommand,
)
from studymate.domain.message_reports import MessageImageReportContext
from studymate.domain.messaging import MessageContent
from studymate.domain.reports import ReportCategory
from studymate.infrastructure.persistence.product_events import record_message_report_event
from studymate.infrastructure.safety.message_reports import SqlMessageReportUnitOfWork
from tests.integration.chat_images.test_display import prepared as image_ready
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.test_message_commands import Chat


@dataclass(frozen=True, slots=True)
class Reports:
    chat: Chat
    context: MessageImageReportContext
    uow: SqlMessageReportUnitOfWork

    def command(self, key: str = "image-report-intent") -> SubmitMessageImageReportCommand:
        return SubmitMessageImageReportCommand(
            self.chat.recipient.credential,
            self.context.id,
            ReportCategory.INAPPROPRIATE_CONTENT,
            IntentKey(key),
            "Private report explanation",
        )

    def submit(self) -> SubmitMessageImageReport:
        return SubmitMessageImageReport(self.uow, HASHER, FINGERPRINTER)


async def prepared(engine: AsyncEngine) -> Reports:
    owned, image, _storage = await image_ready(engine)
    result = await owned.send()(
        replace(
            owned.command(),
            client_message_id=image.client_message_id,
            content=MessageContent("Private image caption", image.id),
        )
    )
    assert result.message is not None
    uow = SqlMessageReportUnitOfWork(owned.api.sessions, record_message_report_event)
    context = await IssueMessageImageReportContext(uow, HASHER)(
        owned.recipient.credential, owned.conversation_id, result.message.id
    )
    return Reports(owned, context, uow)
