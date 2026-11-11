from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import IdentitySnapshot
from studymate.application.messaging.participants import ChatParticipantSource
from studymate.application.messaging.ports import ConversationAccess, MessageIntent
from studymate.domain.messaging import ChatConversation, MessageContent, MessageOperation
from studymate.domain.relationships import AccountPair
from studymate.infrastructure.chat_images.cancellation import cancel_prepared_image
from studymate.infrastructure.chat_images.message_admission import (
    ReadyMessageImageSource,
    admit_message_image,
)
from studymate.infrastructure.observability.tracing import current_origin
from studymate.infrastructure.persistence.chat_participants import read_chat_participants
from studymate.infrastructure.persistence.conversation_models import ConversationRecord
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
    SessionRecord,
)
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.message_models import (
    MessageCommandIntentRecord,
    MessageOperationRecord,
    MessageRecord,
)
from studymate.infrastructure.persistence.message_values import read_message_operation
from studymate.infrastructure.persistence.profile_sources import read_blocked_peers
from studymate.infrastructure.persistence.transactions import open_transaction


class MessageOutcomeRecorder(Protocol):
    async def __call__(self, session: AsyncSession, operation: MessageOperation) -> None: ...


@dataclass(slots=True)
class MessageAuthority:
    actor_id: UUID | None = None
    conversation: ConversationRecord | None = None
    image: ReadyMessageImageSource | None = None
    image_client_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class SqlMessageTransaction(SqlIdentityTransaction):
    conversation_id: UUID
    recorder: MessageOutcomeRecorder
    authority: MessageAuthority = field(default_factory=MessageAuthority)

    def authenticated(self, account_id: UUID) -> None:
        SqlIdentityTransaction.authenticated(self, account_id)
        self.authority.actor_id = account_id

    def check_actor(self, account_id: UUID) -> None:
        if self.authority.actor_id != account_id:
            raise RuntimeError("Message adapter lacks this authenticated participant")

    async def lock_identity(self, secret_digest: bytes) -> IdentitySnapshot | None:
        actor_id = await self.session.scalar(
            select(SessionRecord.account_id).where(SessionRecord.secret_digest == secret_digest)
        )
        scope = (
            await self.session.execute(
                select(ConversationRecord.low_id, ConversationRecord.high_id).where(
                    ConversationRecord.id == self.conversation_id
                )
            )
        ).one_or_none()
        if scope is None or actor_id not in scope:
            return await SqlIdentityTransaction.lock_identity(self, secret_digest)
        peer_id = scope.high_id if actor_id == scope.low_id else scope.low_id
        return await self.lock_identity_for_peer(secret_digest, peer_id)

    async def conversation(
        self, actor_id: UUID, conversation_id: UUID
    ) -> ConversationAccess | None:
        self.check_actor(actor_id)
        if conversation_id != self.conversation_id:
            raise RuntimeError("Conversation differs from the transaction lock scope")
        record = await self.session.scalar(
            select(ConversationRecord)
            .where(
                ConversationRecord.id == conversation_id,
                or_(ConversationRecord.low_id == actor_id, ConversationRecord.high_id == actor_id),
            )
            .with_for_update(read=self.shared_identity_locks)
        )
        if record is None:
            return None
        self.authority.conversation = record
        pair = AccountPair(record.low_id, record.high_id)
        peer_id = pair.high if pair.low == actor_id else pair.low
        peer = await self.session.get(AccountRecord, peer_id)
        if peer is None:
            raise RuntimeError("Accepted conversation lost its retained participant")
        binding = await self.session.get(InstitutionalBindingRecord, peer_id)
        blocked = await read_blocked_peers(self.session, actor_id, (peer_id,))
        return ConversationAccess(
            ChatConversation(
                record.id,
                record.relationship_id,
                pair,
                record.request_id,
                record.accepted_request_version,
                record.next_message_sequence,
            ),
            binding is not None and binding.revoked_at is None,
            peer.banned_at is not None,
            peer.deleted_at is not None,
            peer_id in blocked,
        )

    async def current_participant(self, account_id: UUID) -> ChatParticipantSource | None:
        conversation = self.authority.conversation
        if (
            conversation is None
            or self.authority.actor_id == account_id
            or account_id not in (conversation.low_id, conversation.high_id)
        ):
            raise RuntimeError("Chat identity source lacks its accepted participant scope")
        return (await read_chat_participants(self.session, (account_id,))).get(account_id)

    async def message_intent(
        self, actor_id: UUID, operation: str, key: IntentKey
    ) -> MessageIntent | None:
        self.check_actor(actor_id)
        record = await self.session.get(
            MessageCommandIntentRecord, (actor_id, operation, key.value)
        )
        if record is None:
            return None
        result = await read_message_operation(self.session, record.result_operation_id, actor_id)
        if result is None:
            raise RuntimeError("Retained message receipt lost its owned terminal source")
        return MessageIntent(record.fingerprint, result)

    async def message_operation(
        self, actor_id: UUID, conversation_id: UUID, client_message_id: UUID
    ) -> MessageOperation | None:
        self.check_actor(actor_id)
        if conversation_id != self.conversation_id:
            raise RuntimeError("Message lookup differs from the conversation scope")
        operation_id = await self.session.scalar(
            select(MessageOperationRecord.id).where(
                MessageOperationRecord.conversation_id == conversation_id,
                MessageOperationRecord.author_id == actor_id,
                MessageOperationRecord.client_message_id == client_message_id,
            )
        )
        return (
            await read_message_operation(self.session, operation_id, actor_id)
            if operation_id is not None
            else None
        )

    async def admit_message_content(
        self,
        actor_id: UUID,
        conversation_id: UUID,
        client_message_id: UUID,
        content: MessageContent,
    ) -> None:
        self.check_actor(actor_id)
        conversation = self.authority.conversation
        if conversation is None or conversation.id != conversation_id:
            raise RuntimeError("Image admission lacks its locked accepted conversation")
        self.authority.image = await admit_message_image(
            self.session, actor_id, conversation_id, client_message_id, content
        )
        self.authority.image_client_id = client_message_id

    async def save_message_operation(self, operation: MessageOperation) -> None:
        self.check_actor(operation.author_id)
        conversation = self.authority.conversation
        if (
            conversation is None
            or operation.conversation_id != conversation.id
            or operation.pair != AccountPair(conversation.low_id, conversation.high_id)
        ):
            raise RuntimeError("Message write lacks its locked accepted conversation")
        message = operation.message
        self.session.add(
            MessageOperationRecord(
                id=operation.id,
                conversation_id=conversation.id,
                low_id=operation.pair.low,
                high_id=operation.pair.high,
                author_id=operation.author_id,
                client_message_id=operation.client_message_id,
                state=operation.outcome.value,
                message_id=message.id if message is not None else None,
                cancelled_at=operation.cancelled_at,
            )
        )
        await self.session.flush()
        if message is not None:
            if message.sequence != conversation.next_message_sequence:
                raise RuntimeError("Message admission differs from the locked sequence")
            image = self.authority.image
            if message.content.image_id is not None and (
                image is None
                or image.image_id != message.content.image_id
                or self.authority.image_client_id != message.client_message_id
            ):
                raise RuntimeError("Message image lacks its actual owned Ready admission")
            if message.content.image_id is None and image is not None:
                raise RuntimeError("Text message differs from its actual image admission")
            self.session.add(
                MessageRecord(
                    id=message.id,
                    operation_id=operation.id,
                    conversation_id=conversation.id,
                    low_id=operation.pair.low,
                    high_id=operation.pair.high,
                    author_id=operation.author_id,
                    client_message_id=operation.client_message_id,
                    state="confirmed",
                    sequence=message.sequence,
                    text=message.content.text,
                    image_id=image.image_id if image is not None else None,
                    image_version=image.version if image is not None else None,
                    image_attempt_id=image.attempt_id if image is not None else None,
                    image_state="ready" if image is not None else None,
                    sent_at=message.sent_at,
                )
            )
            conversation.next_message_sequence += 1
            await self.session.flush()
        await self.recorder(self.session, operation)

    async def cancel_image_preparation(self, operation: MessageOperation) -> None:
        self.check_actor(operation.author_id)
        conversation = self.authority.conversation
        if (
            conversation is None
            or operation.conversation_id != conversation.id
            or operation.pair != AccountPair(conversation.low_id, conversation.high_id)
        ):
            raise RuntimeError("Image cancellation lacks its locked accepted conversation")
        await cancel_prepared_image(self.session, operation)

    async def remember_message_intent(
        self, actor_id: UUID, operation: str, key: IntentKey, intent: MessageIntent, at: datetime
    ) -> None:
        self.check_actor(actor_id)
        origin = current_origin()
        self.session.add(
            MessageCommandIntentRecord(
                actor_id=actor_id,
                operation=operation,
                key=key.value,
                conversation_id=self.conversation_id,
                fingerprint=intent.fingerprint,
                result_operation_id=intent.operation.id,
                created_at=at,
                request_id=origin.request_id if origin is not None else None,
                action_id=origin.action_id if origin is not None else None,
                trace_id=origin.trace_id if origin is not None else None,
                span_id=origin.span_id if origin is not None else None,
            )
        )
        await self.session.flush()


@dataclass(frozen=True, slots=True)
class SqlMessageUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: MessageOutcomeRecorder

    @asynccontextmanager
    async def transaction(self, conversation_id: UUID) -> AsyncIterator[SqlMessageTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlMessageTransaction(session, conversation_id, self.recorder)
