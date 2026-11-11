from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.profiles.goals import GoalIntent, GoalTransaction, SavedGoal
from studymate.domain.catalogue import Subject
from studymate.domain.discovery import topic_match_key
from studymate.domain.study_context import (
    CanonicalSubjectRef,
    CustomSubjectRef,
    GoalContent,
    StudyGoal,
)
from studymate.infrastructure.persistence.catalogue import SqlSubjectReader
from studymate.infrastructure.persistence.goal_models import (
    GoalIntentRecord,
    GoalRecord,
    GoalRevisionRecord,
)
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.product_events import (
    record_goal_event,
    record_request_outcome,
)
from studymate.infrastructure.persistence.transactions import open_transaction
from studymate.infrastructure.requests.lifecycle import close_goal_requests


def goal_value(root: GoalRecord, record: GoalRevisionRecord) -> SavedGoal:
    subject = (
        CanonicalSubjectRef(record.subject_id)
        if record.subject_id is not None
        else CustomSubjectRef(record.subject_label)
    )
    return SavedGoal(
        StudyGoal(
            root.id,
            root.account_id,
            record.version,
            GoalContent(subject, record.topic, record.context, record.shared_learning),
            root.created_at,
            record.saved_at,
            record.completed_at,
        ),
        record.subject_label,
    )


@dataclass(frozen=True, slots=True)
class SqlGoalTransaction(SqlIdentityTransaction):
    async def active_goal(self, account_id: UUID) -> SavedGoal | None:
        row = (
            await self.session.execute(
                select(GoalRecord, GoalRevisionRecord)
                .join(
                    GoalRevisionRecord,
                    (GoalRevisionRecord.goal_id == GoalRecord.id)
                    & (GoalRevisionRecord.version == GoalRecord.current_version),
                )
                .where(GoalRecord.account_id == account_id, GoalRecord.completed_at.is_(None))
            )
        ).one_or_none()
        return goal_value(*row) if row is not None else None

    async def goal_version(self, account_id: UUID, goal_id: UUID, version: int) -> SavedGoal | None:
        row = (
            await self.session.execute(
                select(GoalRecord, GoalRevisionRecord)
                .join(GoalRevisionRecord, GoalRevisionRecord.goal_id == GoalRecord.id)
                .where(
                    GoalRecord.account_id == account_id,
                    GoalRecord.id == goal_id,
                    GoalRevisionRecord.version == version,
                )
            )
        ).one_or_none()
        return goal_value(*row) if row is not None else None

    async def goal_intent(self, account_id: UUID, key: IntentKey) -> GoalIntent | None:
        record = await self.session.get(GoalIntentRecord, (account_id, key.value))
        return (
            GoalIntent(record.fingerprint, record.goal_id, record.result_version)
            if record is not None
            else None
        )

    async def subject(self, subject_id: UUID) -> Subject | None:
        return await SqlSubjectReader(self.session).get(subject_id, lock=True)

    async def save_goal(self, goal: SavedGoal) -> None:
        value, content = goal.goal, goal.goal.content
        if value.version == 1:
            self.session.add(
                GoalRecord(
                    id=value.id,
                    account_id=value.account_id,
                    current_version=value.version,
                    created_at=value.created_at,
                    completed_at=value.completed_at,
                )
            )
            await self.session.flush()
        self.session.add(
            GoalRevisionRecord(
                goal_id=value.id,
                account_id=value.account_id,
                version=value.version,
                subject_id=content.canonical_subject_id,
                subject_label=goal.subject_label,
                topic=content.topic,
                topic_match_key=topic_match_key(content.topic),
                context=content.context,
                shared_learning=content.shared_learning,
                saved_at=value.updated_at,
                completed_at=value.completed_at,
            )
        )
        await self.session.flush()
        if value.version != 1:
            await self.session.execute(
                update(GoalRecord)
                .where(GoalRecord.id == value.id, GoalRecord.account_id == value.account_id)
                .values(current_version=value.version, completed_at=value.completed_at)
            )

        await record_goal_event(self.session, value)
        if not value.active:
            await close_goal_requests(
                self.session, value.account_id, value.id, value.account_id, record_request_outcome
            )

    async def remember_goal_intent(
        self, account_id: UUID, key: IntentKey, intent: GoalIntent, at: datetime
    ) -> None:
        self.session.add(
            GoalIntentRecord(
                account_id=account_id,
                key=key.value,
                fingerprint=intent.fingerprint,
                goal_id=intent.goal_id,
                result_version=intent.result_version,
                created_at=at,
            )
        )
        await self.session.flush()


@dataclass(frozen=True, slots=True)
class SqlGoalUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[GoalTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlGoalTransaction(session)
