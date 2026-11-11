from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.messaging.read_positions import ReadPositionIntent
from studymate.domain.message_reads import ConversationReadPosition
from studymate.domain.relationships import AccountPair
from studymate.infrastructure.observability.tracing import current_origin
from studymate.infrastructure.persistence.message_models import MessageRecord
from studymate.infrastructure.persistence.message_read_models import (
    ConversationReadIntentRecord,
    ConversationReadPositionRecord,
    ConversationReadRevisionRecord,
)
from studymate.infrastructure.persistence.messaging import (
    MessageOutcomeRecorder,
    SqlMessageTransaction,
)
from studymate.infrastructure.persistence.transactions import open_transaction


class ReadPositionRecorder(Protocol):
    async def __call__(self, session: AsyncSession, position: ConversationReadPosition) -> None: ...


def read_position_value(record: ConversationReadRevisionRecord) -> ConversationReadPosition:
    return ConversationReadPosition(
        record.id,
        record.conversation_id,
        AccountPair(record.low_id, record.high_id),
        record.account_id,
        record.version,
        record.through_sequence,
        record.acknowledged_at,
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class SqlReadPositionTransaction(SqlMessageTransaction):
    read_recorder: ReadPositionRecorder

    def check_scope(self, actor_id: UUID, conversation_id: UUID) -> None:
        self.check_actor(actor_id)
        if self.authority.conversation is None or self.authority.conversation.id != conversation_id:
            raise RuntimeError("Read marker lacks its locked accepted conversation")

    async def read_position(
        self, actor_id: UUID, conversation_id: UUID
    ) -> ConversationReadPosition | None:
        self.check_scope(actor_id, conversation_id)
        record = await self.session.scalar(
            select(ConversationReadRevisionRecord)
            .join(
                ConversationReadPositionRecord,
                (
                    ConversationReadPositionRecord.conversation_id
                    == ConversationReadRevisionRecord.conversation_id
                )
                & (
                    ConversationReadPositionRecord.account_id
                    == ConversationReadRevisionRecord.account_id
                )
                & (
                    ConversationReadPositionRecord.current_version
                    == ConversationReadRevisionRecord.version
                ),
            )
            .where(
                ConversationReadRevisionRecord.account_id == actor_id,
                ConversationReadRevisionRecord.conversation_id == conversation_id,
            )
        )
        return read_position_value(record) if record is not None else None

    async def read_position_intent(
        self, actor_id: UUID, key: IntentKey
    ) -> ReadPositionIntent | None:
        self.check_actor(actor_id)
        intent = await self.session.get(ConversationReadIntentRecord, (actor_id, key.value))
        if intent is None:
            return None
        record = await self.session.scalar(
            select(ConversationReadRevisionRecord).where(
                ConversationReadRevisionRecord.id == intent.result_revision_id,
                ConversationReadRevisionRecord.account_id == actor_id,
                ConversationReadRevisionRecord.conversation_id == intent.conversation_id,
            )
        )
        if record is None:
            raise RuntimeError("Read intent lost its actual retained owned source")
        return ReadPositionIntent(intent.fingerprint, read_position_value(record))

    async def message_sequence_exists(self, conversation_id: UUID, sequence: int) -> bool:
        actor_id = self.authority.actor_id
        if actor_id is None:
            raise RuntimeError("Message sequence lookup lacks its authenticated actor")
        self.check_scope(actor_id, conversation_id)
        return bool(
            await self.session.scalar(
                select(
                    select(MessageRecord.id)
                    .where(
                        MessageRecord.conversation_id == conversation_id,
                        MessageRecord.sequence == sequence,
                    )
                    .exists()
                )
            )
        )

    async def save_read_position(self, position: ConversationReadPosition) -> None:
        self.check_scope(position.account_id, position.conversation_id)
        conversation = self.authority.conversation
        if (
            conversation is None
            or position.pair != AccountPair(conversation.low_id, conversation.high_id)
            or position.through_sequence >= conversation.next_message_sequence
        ):
            raise RuntimeError("Read source differs from the actual locked message range")
        root = await self.session.get(
            ConversationReadPositionRecord, (position.conversation_id, position.account_id)
        )
        if root is None:
            if position.version != 1:
                raise RuntimeError("Initial read revision must be the first actual acknowledgement")
            self.session.add(
                ConversationReadPositionRecord(
                    conversation_id=position.conversation_id,
                    account_id=position.account_id,
                    current_version=position.version,
                )
            )
        else:
            previous = await self.read_position(position.account_id, position.conversation_id)
            if (
                previous is None
                or position.version != previous.version + 1
                or position.through_sequence <= previous.through_sequence
            ):
                raise RuntimeError("Read position cannot regress or skip its retained revision")
            root.current_version = position.version
        origin = current_origin()
        self.session.add(
            ConversationReadRevisionRecord(
                id=position.id,
                conversation_id=position.conversation_id,
                account_id=position.account_id,
                version=position.version,
                low_id=position.pair.low,
                high_id=position.pair.high,
                through_sequence=position.through_sequence,
                acknowledged_at=position.acknowledged_at,
                request_id=origin.request_id if origin is not None else None,
                action_id=origin.action_id if origin is not None else None,
                trace_id=origin.trace_id if origin is not None else None,
                span_id=origin.span_id if origin is not None else None,
            )
        )
        await self.session.flush()
        await self.read_recorder(self.session, position)

    async def remember_read_position(
        self, actor_id: UUID, key: IntentKey, intent: ReadPositionIntent, at: datetime
    ) -> None:
        self.check_scope(actor_id, intent.result.conversation_id)
        origin = current_origin()
        self.session.add(
            ConversationReadIntentRecord(
                account_id=actor_id,
                key=key.value,
                conversation_id=intent.result.conversation_id,
                fingerprint=intent.fingerprint,
                result_revision_id=intent.result.id,
                created_at=at,
                request_id=origin.request_id if origin is not None else None,
                action_id=origin.action_id if origin is not None else None,
                trace_id=origin.trace_id if origin is not None else None,
                span_id=origin.span_id if origin is not None else None,
            )
        )
        await self.session.flush()


@dataclass(frozen=True, slots=True)
class SqlReadPositionUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    message_recorder: MessageOutcomeRecorder
    read_recorder: ReadPositionRecorder

    @asynccontextmanager
    async def transaction(self, conversation_id: UUID) -> AsyncIterator[SqlReadPositionTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlReadPositionTransaction(
                session, conversation_id, self.message_recorder, read_recorder=self.read_recorder
            )
