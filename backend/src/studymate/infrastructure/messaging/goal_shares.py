"""Schema0033 adapters; main composes the actual canonical recorder and lifecycle."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.messaging.goal_shares import (
    GOAL_SHARE_PAGE_SIZE,
    AcceptedGoalBaseline,
    GoalShareIntent,
    GoalShareWindow,
)
from studymate.application.profiles.goals import SavedGoal
from studymate.domain.goal_shares import GoalShare, GoalShareState
from studymate.domain.relationships import AccountPair
from studymate.domain.requests.states import RequestState
from studymate.infrastructure.messaging.goal_share_models import (
    ConversationGoalShareHeadRecord,
    ConversationGoalShareIntentRecord,
    ConversationGoalShareRecord,
)
from studymate.infrastructure.observability.tracing import current_origin
from studymate.infrastructure.persistence.conversation_models import ConversationRecord
from studymate.infrastructure.persistence.goal_models import GoalRecord, GoalRevisionRecord
from studymate.infrastructure.persistence.goals import SqlGoalTransaction, goal_value
from studymate.infrastructure.persistence.messaging import (
    MessageOutcomeRecorder,
    SqlMessageTransaction,
)
from studymate.infrastructure.persistence.transactions import open_transaction
from studymate.infrastructure.requests.reads import read_request


class GoalShareRecorder(Protocol):
    async def __call__(self, session: AsyncSession, share: GoalShare) -> None: ...


def source_statement(
    actor_id: UUID, conversation_id: UUID
) -> Select[ConversationGoalShareRecord, GoalRecord, GoalRevisionRecord]:
    share = ConversationGoalShareRecord
    return (
        select(share, GoalRecord, GoalRevisionRecord)
        .join(ConversationRecord, ConversationRecord.id == share.conversation_id)
        .join(
            GoalRecord,
            and_(GoalRecord.id == share.goal_id, GoalRecord.account_id == share.owner_id),
        )
        .join(
            GoalRevisionRecord,
            and_(
                GoalRevisionRecord.account_id == share.owner_id,
                GoalRevisionRecord.goal_id == share.goal_id,
                GoalRevisionRecord.version == share.goal_version,
            ),
        )
        .where(
            share.conversation_id == conversation_id,
            or_(ConversationRecord.low_id == actor_id, ConversationRecord.high_id == actor_id),
        )
    )


def share_value(
    record: ConversationGoalShareRecord, root: GoalRecord, revision: GoalRevisionRecord
) -> GoalShare:
    source = goal_value(root, revision)
    return GoalShare(
        record.id,
        record.conversation_id,
        AccountPair(record.low_id, record.high_id),
        record.owner_id,
        record.context_version,
        source.goal,
        source.subject_label,
        record.shared_at,
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class SqlGoalShareTransaction(SqlMessageTransaction):
    share_recorder: GoalShareRecorder

    def checked_conversation(self, actor_id: UUID, conversation_id: UUID) -> ConversationRecord:
        self.check_actor(actor_id)
        conversation = self.authority.conversation
        if (
            conversation is None
            or conversation.id != conversation_id
            or conversation_id != self.conversation_id
        ):
            raise RuntimeError("Goal sharing lacks its accepted conversation scope")
        return conversation

    async def active_goal(self, account_id: UUID) -> SavedGoal | None:
        self.check_actor(account_id)
        return await SqlGoalTransaction(self.session).active_goal(account_id)

    async def goal_version(self, account_id: UUID, goal_id: UUID, version: int) -> SavedGoal | None:
        self.check_actor(account_id)
        return await SqlGoalTransaction(self.session).goal_version(account_id, goal_id, version)

    async def goal_share_state(self, actor_id: UUID, conversation_id: UUID) -> GoalShareState:
        self.checked_conversation(actor_id, conversation_id)
        head = await self.session.get(ConversationGoalShareHeadRecord, conversation_id)
        if head is None:
            return GoalShareState(0, None)
        row = (
            await self.session.execute(
                source_statement(actor_id, conversation_id).where(
                    ConversationGoalShareRecord.context_version == head.context_version
                )
            )
        ).one_or_none()
        if row is None:
            raise RuntimeError("Goal context head lost its actual retained source")
        return GoalShareState(head.context_version, share_value(*row))

    async def accepted_goal_baseline(
        self, actor_id: UUID, conversation_id: UUID
    ) -> AcceptedGoalBaseline:
        conversation = self.checked_conversation(actor_id, conversation_id)
        source = await read_request(
            self.session, conversation.request_id, conversation.accepted_request_version
        )
        if (
            source is None
            or source.state != RequestState.ACCEPTED
            or source.conversation_id != conversation_id
            or source.pair != AccountPair(conversation.low_id, conversation.high_id)
        ):
            raise RuntimeError("Accepted goal context lost its actual request source")
        return AcceptedGoalBaseline(source.id, source.version, source.context)

    async def goal_share_history(
        self, actor_id: UUID, conversation_id: UUID, window: GoalShareWindow
    ) -> tuple[GoalShare, ...]:
        self.checked_conversation(actor_id, conversation_id)
        statement = source_statement(actor_id, conversation_id).where(
            ConversationGoalShareRecord.context_version <= window.anchor_version
        )
        if window.before_version is not None:
            statement = statement.where(
                ConversationGoalShareRecord.context_version < window.before_version
            )
        rows = (
            await self.session.execute(
                statement.order_by(ConversationGoalShareRecord.context_version.desc()).limit(
                    GOAL_SHARE_PAGE_SIZE + 1
                )
            )
        ).all()
        return tuple(share_value(*row) for row in rows)

    async def goal_share_intent(self, actor_id: UUID, key: IntentKey) -> GoalShareIntent | None:
        self.check_actor(actor_id)
        intent = await self.session.get(ConversationGoalShareIntentRecord, (actor_id, key.value))
        if intent is None:
            return None
        # Own prior may belong to another conversation: return its fingerprint
        # for the use-case conflict check, never a false missing/new intent.
        row = (
            await self.session.execute(
                source_statement(actor_id, intent.conversation_id).where(
                    ConversationGoalShareRecord.id == intent.result_share_id,
                    ConversationGoalShareRecord.owner_id == actor_id,
                )
            )
        ).one_or_none()
        if row is None:
            raise RuntimeError("Goal share intent lost its original owned source")
        return GoalShareIntent(intent.fingerprint, share_value(*row))

    async def save_goal_share(self, share: GoalShare) -> None:
        conversation = self.checked_conversation(share.owner_id, share.conversation_id)
        if share.pair != AccountPair(conversation.low_id, conversation.high_id):
            raise RuntimeError("Goal share source belongs to another accepted pair")
        head = await self.session.get(ConversationGoalShareHeadRecord, conversation.id)
        expected = 1 if head is None else head.context_version + 1
        if share.context_version != expected:
            raise RuntimeError("Goal share source does not advance the locked context")
        origin = current_origin()
        self.session.add(
            ConversationGoalShareRecord(
                id=share.id,
                conversation_id=share.conversation_id,
                low_id=share.pair.low,
                high_id=share.pair.high,
                owner_id=share.owner_id,
                goal_id=share.goal.id,
                goal_version=share.goal.version,
                context_version=share.context_version,
                shared_at=share.shared_at,
                http_request_id=origin.request_id if origin is not None else None,
                action_id=origin.action_id if origin is not None else None,
                trace_id=origin.trace_id if origin is not None else None,
                span_id=origin.span_id if origin is not None else None,
            )
        )
        await self.session.flush()
        if head is None:
            self.session.add(
                ConversationGoalShareHeadRecord(
                    conversation_id=conversation.id, context_version=share.context_version
                )
            )
        else:
            head.context_version = share.context_version
        await self.session.flush()
        await self.share_recorder(self.session, share)

    async def remember_goal_share(
        self, actor_id: UUID, key: IntentKey, intent: GoalShareIntent, at: datetime
    ) -> None:
        self.checked_conversation(actor_id, intent.result.conversation_id)
        if intent.result.owner_id != actor_id:
            raise RuntimeError("Goal share receipt is not the actual actors source")
        origin = current_origin()
        self.session.add(
            ConversationGoalShareIntentRecord(
                actor_id=actor_id,
                key=key.value,
                conversation_id=intent.result.conversation_id,
                fingerprint=intent.fingerprint,
                result_share_id=intent.result.id,
                created_at=at,
                http_request_id=origin.request_id if origin is not None else None,
                action_id=origin.action_id if origin is not None else None,
                trace_id=origin.trace_id if origin is not None else None,
                span_id=origin.span_id if origin is not None else None,
            )
        )
        await self.session.flush()


@dataclass(frozen=True, slots=True)
class SqlGoalShareUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    message_recorder: MessageOutcomeRecorder
    share_recorder: GoalShareRecorder

    @asynccontextmanager
    async def transaction(self, conversation_id: UUID) -> AsyncIterator[SqlGoalShareTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlGoalShareTransaction(
                session, conversation_id, self.message_recorder, share_recorder=self.share_recorder
            )
