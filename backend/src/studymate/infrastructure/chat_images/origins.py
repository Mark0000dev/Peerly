"""Correlation from the actual first queue transaction, never a retry or inferred source."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from studymate.domain.chat_images import ChatImagePreparation, ChatImageState
from studymate.infrastructure.observability.origin import ExecutionOrigin
from studymate.infrastructure.observability.tracing import current_origin
from studymate.infrastructure.persistence.base import Base


class ChatImageQueueOriginRecord(Base):
    __tablename__ = "chat_image_queue_origins"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "conversation_id", "client_message_id", "image_id", "version", "state"],
            [
                "chat_image_revisions.account_id",
                "chat_image_revisions.conversation_id",
                "chat_image_revisions.client_message_id",
                "chat_image_revisions.image_id",
                "chat_image_revisions.version",
                "chat_image_revisions.state",
            ],
            name="fk_chat_image_queue_origin_owned_revision",
            ondelete="RESTRICT",
        ),
        CheckConstraint("state='queued' AND version>0", name="actual_queued_revision"),
        CheckConstraint(
            "(trace_id IS NULL AND span_id IS NULL) OR "
            "(trace_id IS NOT NULL AND span_id IS NOT NULL AND "
            "trace_id ~ '^[0-9a-f]{32}$' AND trace_id != repeat('0',32) AND "
            "span_id ~ '^[0-9a-f]{16}$' AND span_id != repeat('0',16))",
            name="origin_trace_pair",
        ),
    )
    image_id: Mapped[UUID] = mapped_column(primary_key=True)
    account_id: Mapped[UUID] = mapped_column()
    conversation_id: Mapped[UUID] = mapped_column()
    client_message_id: Mapped[UUID] = mapped_column()
    version: Mapped[int] = mapped_column()
    state: Mapped[str] = mapped_column(String(16))
    request_id: Mapped[UUID] = mapped_column()
    action_id: Mapped[UUID | None] = mapped_column()
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


async def remember_image_queue_origin(session: AsyncSession, image: ChatImagePreparation) -> None:
    if image.state != ChatImageState.QUEUED:
        raise ValueError("Execution origin must belong to the actual queued image revision")
    origin = current_origin()
    if origin is None:
        return
    prior = await session.get(ChatImageQueueOriginRecord, image.id)
    if prior is not None:
        raise RuntimeError("The first image queue origin cannot be replaced by a retry")
    session.add(
        ChatImageQueueOriginRecord(
            image_id=image.id,
            account_id=image.account_id,
            conversation_id=image.conversation_id,
            client_message_id=image.client_message_id,
            version=image.version,
            state=image.state.value,
            request_id=origin.request_id,
            action_id=origin.action_id,
            trace_id=origin.trace_id,
            span_id=origin.span_id,
            recorded_at=image.updated_at,
        )
    )
    await session.flush()


async def read_image_queue_origin(session: AsyncSession, image_id: UUID) -> ExecutionOrigin | None:
    source = await session.get(ChatImageQueueOriginRecord, image_id)
    if source is None:
        return None
    return ExecutionOrigin(source.request_id, source.action_id, source.trace_id, source.span_id)
