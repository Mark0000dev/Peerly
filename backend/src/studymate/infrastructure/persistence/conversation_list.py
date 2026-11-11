"""One bounded SQL snapshot for thread rows and current minimal peer identity."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import DateTime, Nullable, case, func, or_, select, tuple_, type_coerce
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.messaging.conversation_list import (
    CONVERSATION_PAGE_SIZE,
    ConversationListEntry,
    ConversationListQuery,
)
from studymate.application.messaging.participants import (
    ChatParticipantSource,
    chat_participant_projection,
)
from studymate.application.messaging.ports import ConversationAccess
from studymate.domain.media import MediaObjectKind, MediaObjectRef
from studymate.domain.messaging import ChatConversation, ConfirmedMessage, MessageContent
from studymate.domain.profiles import DisplayName
from studymate.domain.relationships import AccountPair
from studymate.infrastructure.persistence.block_models import BlockRecord, BlockRevisionRecord
from studymate.infrastructure.persistence.conversation_models import ConversationRecord
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
)
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.media_models import (
    PhotoRecord,
    PhotoRevisionRecord,
    PhotoUploadRevisionRecord,
)
from studymate.infrastructure.persistence.message_models import MessageRecord
from studymate.infrastructure.persistence.message_read_models import (
    ConversationReadPositionRecord,
    ConversationReadRevisionRecord,
)
from studymate.infrastructure.persistence.profile_models import ProfileRecord, ProfileRevisionRecord
from studymate.infrastructure.persistence.transactions import open_transaction
from studymate.infrastructure.requests.models import (
    ConnectionRequestRecord,
    RequestPreviewRecord,
    RequestRevisionRecord,
)
from studymate.infrastructure.requests.values import request_value


@dataclass(slots=True)
class ListAuthority:
    actor_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class SqlConversationListTransaction(SqlIdentityTransaction):
    authority: ListAuthority = field(default_factory=ListAuthority)

    def authenticated(self, account_id: UUID) -> None:
        SqlIdentityTransaction.authenticated(self, account_id)
        self.authority.actor_id = account_id

    async def list_conversations(
        self, query: ConversationListQuery
    ) -> tuple[ConversationListEntry, ...]:
        if query.actor_id != self.authority.actor_id:
            raise RuntimeError("Conversation list lacks its actual authenticated participant")
        conversation = ConversationRecord
        revision = RequestRevisionRecord
        message = MessageRecord
        peer_id = case(
            (conversation.low_id == query.actor_id, conversation.high_id), else_=conversation.low_id
        )
        activity = type_coerce(
            func.greatest(
                revision.changed_at,
                select(func.max(message.sent_at))
                .where(message.conversation_id == conversation.id, message.sent_at <= query.as_of)
                .correlate(conversation)
                .scalar_subquery(),
            ),
            DateTime(timezone=True),
        )
        latest = (
            select(message.id)
            .where(message.conversation_id == conversation.id, message.sent_at <= query.as_of)
            .order_by(message.sequence.desc())
            .limit(1)
            .correlate(conversation)
            .scalar_subquery()
        )
        blocked = (
            select(BlockRecord.relationship_id)
            .join(
                BlockRevisionRecord,
                (BlockRevisionRecord.relationship_id == BlockRecord.relationship_id)
                & (BlockRevisionRecord.blocker_id == BlockRecord.blocker_id)
                & (BlockRevisionRecord.version == BlockRecord.current_version),
            )
            .where(
                BlockRecord.relationship_id == conversation.relationship_id,
                BlockRevisionRecord.blocked.is_(True),
            )
            .correlate(conversation)
            .exists()
        )
        unread = (
            select(func.count())
            .select_from(message)
            .where(
                message.conversation_id == conversation.id,
                message.author_id != query.actor_id,
                message.sent_at <= query.as_of,
                message.sequence
                > func.coalesce(ConversationReadRevisionRecord.through_sequence, 0),
            )
            .correlate(conversation, ConversationReadRevisionRecord)
            .scalar_subquery()
        )
        statement = (
            select(
                conversation,
                ConnectionRequestRecord,
                revision,
                RequestPreviewRecord,
                AccountRecord,
                Nullable(InstitutionalBindingRecord),
                Nullable(ProfileRevisionRecord),
                Nullable(PhotoRevisionRecord),
                Nullable(PhotoUploadRevisionRecord),
                Nullable(message),
                unread,
                blocked,
                activity,
            )
            .select_from(conversation)
            .join(
                ConnectionRequestRecord,
                ConnectionRequestRecord.id == conversation.request_id,
            )
            .join(
                revision,
                (revision.request_id == conversation.request_id)
                & (revision.version == conversation.accepted_request_version),
            )
            .join(
                RequestPreviewRecord,
                RequestPreviewRecord.id == ConnectionRequestRecord.preview_id,
            )
            .join(AccountRecord, AccountRecord.id == peer_id)
            .outerjoin(
                InstitutionalBindingRecord,
                InstitutionalBindingRecord.account_id == peer_id,
            )
            .outerjoin(ProfileRecord, ProfileRecord.account_id == peer_id)
            .outerjoin(
                ProfileRevisionRecord,
                (ProfileRevisionRecord.account_id == peer_id)
                & (ProfileRevisionRecord.version == ProfileRecord.current_version),
            )
            .outerjoin(PhotoRecord, PhotoRecord.account_id == peer_id)
            .outerjoin(
                PhotoRevisionRecord,
                (PhotoRevisionRecord.account_id == peer_id)
                & (PhotoRevisionRecord.version == PhotoRecord.current_version),
            )
            .outerjoin(
                PhotoUploadRevisionRecord,
                (PhotoUploadRevisionRecord.account_id == peer_id)
                & (PhotoUploadRevisionRecord.upload_id == PhotoRevisionRecord.upload_id)
                & (PhotoUploadRevisionRecord.version == PhotoRevisionRecord.upload_version)
                & (PhotoUploadRevisionRecord.state == "ready"),
            )
            .outerjoin(message, message.id == latest)
            .outerjoin(
                ConversationReadPositionRecord,
                (ConversationReadPositionRecord.conversation_id == conversation.id)
                & (ConversationReadPositionRecord.account_id == query.actor_id),
            )
            .outerjoin(
                ConversationReadRevisionRecord,
                (ConversationReadRevisionRecord.conversation_id == conversation.id)
                & (ConversationReadRevisionRecord.account_id == query.actor_id)
                & (
                    ConversationReadRevisionRecord.version
                    == ConversationReadPositionRecord.current_version
                ),
            )
            .where(
                or_(conversation.low_id == query.actor_id, conversation.high_id == query.actor_id),
                activity <= query.as_of,
            )
        )
        if query.cursor is not None:
            statement = statement.where(
                tuple_(activity, conversation.id)
                < tuple_(query.cursor.activity_at, query.cursor.conversation_id)
            )
        rows = await self.session.execute(
            statement.order_by(activity.desc(), conversation.id.desc()).limit(
                CONVERSATION_PAGE_SIZE + 1
            )
        )
        result: list[ConversationListEntry] = []
        for (
            thread,
            root,
            accepted,
            preview,
            peer,
            binding,
            profile,
            photo,
            upload,
            last,
            unread_count,
            is_blocked,
            activity_at,
        ) in rows:
            pair = AccountPair(thread.low_id, thread.high_id)
            access = ConversationAccess(
                ChatConversation(
                    thread.id,
                    thread.relationship_id,
                    pair,
                    thread.request_id,
                    thread.accepted_request_version,
                    thread.next_message_sequence,
                ),
                binding is not None and binding.revoked_at is None,
                peer.banned_at is not None,
                peer.deleted_at is not None,
                is_blocked,
            )
            photo_ready = photo is not None and upload is not None and upload.attempt_id is not None
            source = ChatParticipantSource(
                peer.id,
                DisplayName(profile.display_name)
                if profile is not None and profile.display_name is not None
                else None,
                photo.version if photo_ready and photo is not None else None,
                MediaObjectRef(upload.upload_id, MediaObjectKind.DISPLAY, upload.attempt_id)
                if photo_ready and upload is not None and upload.attempt_id is not None
                else None,
            )
            original = request_value(root, accepted, preview)
            result.append(
                ConversationListEntry(
                    thread.id,
                    original.id,
                    original.changed_at,
                    activity_at,
                    chat_participant_projection(access, query.actor_id, source),
                    original.context,
                    ConfirmedMessage(
                        last.id,
                        last.operation_id,
                        thread.id,
                        pair,
                        last.author_id,
                        last.client_message_id,
                        last.sequence,
                        MessageContent(last.text, last.image_id),
                        last.sent_at,
                    )
                    if last is not None
                    else None,
                    unread_count,
                    access.can_send,
                )
            )
        return tuple(result)


@dataclass(frozen=True, slots=True)
class SqlConversationListUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlConversationListTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlConversationListTransaction(session)
