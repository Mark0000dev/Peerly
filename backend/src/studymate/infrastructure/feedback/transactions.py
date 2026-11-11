"""Real same-session accepted-pair feedback transactions; no external calls."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.feedback.ports import FeedbackIntent, FeedbackOperation
from studymate.application.idempotency import IntentKey
from studymate.domain.feedback.assessments import CurrentFeedback, FeedbackRevision
from studymate.domain.feedback.interaction import InteractionEvidence
from studymate.domain.feedback.outcomes import StudyOutcomeRevision, StudyPromptReceipt
from studymate.infrastructure.feedback.models import (
    FeedbackCommandIntentRecord,
    PeerFeedbackRecord,
    PeerFeedbackRemovalRecord,
    PeerFeedbackRevisionRecord,
    StudyOutcomeRecord,
    StudyOutcomeRevisionRecord,
    StudyPromptReceiptRecord,
)
from studymate.infrastructure.feedback.values import (
    assign_origin,
    feedback_value,
    human_source,
    interaction_value,
    outcome_value,
    prompt_value,
    removal_value,
)
from studymate.infrastructure.persistence.conversation_models import ConversationRecord
from studymate.infrastructure.persistence.messaging import SqlMessageTransaction
from studymate.infrastructure.persistence.product_events import record_message_outcome
from studymate.infrastructure.persistence.transactions import open_transaction


class StudyOutcomeRecorder(Protocol):
    async def __call__(self, session: AsyncSession, revision: StudyOutcomeRevision) -> None: ...


class PeerFeedbackRecorder(Protocol):
    async def __call__(self, session: AsyncSession, revision: FeedbackRevision) -> None: ...


class StudyPromptRecorder(Protocol):
    async def __call__(self, session: AsyncSession, receipt: StudyPromptReceipt) -> None: ...


@dataclass(frozen=True, slots=True)
class FeedbackRecorders:
    outcome: StudyOutcomeRecorder
    assessment: PeerFeedbackRecorder
    prompt: StudyPromptRecorder


@dataclass(frozen=True, slots=True, kw_only=True)
class SqlFeedbackTransaction(SqlMessageTransaction):
    feedback_recorders: FeedbackRecorders

    def checked_conversation(self, actor_id: UUID, conversation_id: UUID) -> ConversationRecord:
        self.check_actor(actor_id)
        row = self.authority.conversation
        if row is None or row.id != conversation_id or actor_id not in (row.low_id, row.high_id):
            raise RuntimeError("Feedback lacks its actual locked accepted participant scope")
        return row

    async def interaction(self, actor_id: UUID, conversation_id: UUID) -> InteractionEvidence:
        conversation = self.checked_conversation(actor_id, conversation_id)
        low = await human_source(self.session, conversation_id, conversation.low_id)
        high = await human_source(self.session, conversation_id, conversation.high_id)
        return await interaction_value(self.session, conversation, low, high)

    async def study_outcome(
        self, actor_id: UUID, conversation_id: UUID
    ) -> StudyOutcomeRevision | None:
        self.checked_conversation(actor_id, conversation_id)
        row = await self.session.scalar(
            select(StudyOutcomeRevisionRecord)
            .join(
                StudyOutcomeRecord,
                (StudyOutcomeRecord.conversation_id == StudyOutcomeRevisionRecord.conversation_id)
                & (StudyOutcomeRecord.actor_id == StudyOutcomeRevisionRecord.actor_id)
                & (StudyOutcomeRecord.current_version == StudyOutcomeRevisionRecord.version),
            )
            .where(
                StudyOutcomeRecord.conversation_id == conversation_id,
                StudyOutcomeRecord.actor_id == actor_id,
            )
        )
        return outcome_value(row) if row is not None else None

    async def current_feedback(self, reviewer_id: UUID, partner_id: UUID) -> CurrentFeedback | None:
        conversation = self.checked_conversation(reviewer_id, self.conversation_id)
        if (
            partner_id not in (conversation.low_id, conversation.high_id)
            or partner_id == reviewer_id
        ):
            raise RuntimeError("Feedback target differs from its actual accepted partner")
        root = await self.session.scalar(
            select(PeerFeedbackRecord)
            .where(
                PeerFeedbackRecord.reviewer_id == reviewer_id,
                PeerFeedbackRecord.partner_id == partner_id,
            )
            .with_for_update()
        )
        if root is None:
            return None
        row = await self.session.get(PeerFeedbackRevisionRecord, (root.id, root.current_version))
        if row is None:
            raise RuntimeError("Current feedback lost its retained revision")
        removal = (
            await self.session.get(PeerFeedbackRemovalRecord, root.current_removal_id)
            if root.current_removal_id is not None
            else None
        )
        if root.current_removal_id is not None and removal is None:
            raise RuntimeError("Feedback lost its actual retained moderation source")
        return CurrentFeedback(
            await feedback_value(self.session, row),
            removal_value(removal) if removal is not None else None,
        )

    async def prompt_receipt(
        self, actor_id: UUID, conversation_id: UUID
    ) -> StudyPromptReceipt | None:
        self.checked_conversation(actor_id, conversation_id)
        row = await self.session.scalar(
            select(StudyPromptReceiptRecord).where(
                StudyPromptReceiptRecord.actor_id == actor_id,
                StudyPromptReceiptRecord.conversation_id == conversation_id,
            )
        )
        return prompt_value(row) if row is not None else None

    async def feedback_intent(
        self, actor_id: UUID, operation: FeedbackOperation, key: IntentKey
    ) -> FeedbackIntent | None:
        self.checked_conversation(actor_id, self.conversation_id)
        row = await self.session.get(
            FeedbackCommandIntentRecord, (actor_id, operation.value, key.value)
        )
        if row is None:
            return None
        result: StudyOutcomeRevision | FeedbackRevision | StudyPromptReceipt | None
        if row.result_kind == "outcome":
            source = await self.session.get(StudyOutcomeRevisionRecord, row.outcome_id)
            if source is None:
                raise RuntimeError("Outcome intent lost its retained result")
            result = outcome_value(source)
        elif row.result_kind == "assessment":
            assessment = await self.session.get(
                PeerFeedbackRevisionRecord, (row.feedback_id, row.feedback_version)
            )
            if assessment is None:
                raise RuntimeError("Assessment intent lost its retained result")
            result = await feedback_value(self.session, assessment)
        elif row.result_kind == "prompt":
            prompt = await self.session.get(StudyPromptReceiptRecord, row.prompt_id)
            if prompt is None:
                raise RuntimeError("Prompt intent lost its retained result")
            result = prompt_value(prompt)
        elif row.result_kind == "no_offer":
            result = None
        else:
            raise RuntimeError("Feedback intent has an unknown retained result kind")
        return FeedbackIntent(row.fingerprint, result)

    async def remember_feedback_intent(
        self, actor_id: UUID, operation: FeedbackOperation, key: IntentKey, intent: FeedbackIntent
    ) -> None:
        conversation = self.checked_conversation(actor_id, self.conversation_id)
        result = intent.result
        kind = (
            "outcome"
            if isinstance(result, StudyOutcomeRevision)
            else "assessment"
            if isinstance(result, FeedbackRevision)
            else "prompt"
            if isinstance(result, StudyPromptReceipt)
            else "no_offer"
        )
        self.session.add(
            FeedbackCommandIntentRecord(
                actor_id=actor_id,
                operation=operation.value,
                key=key.value,
                fingerprint=intent.fingerprint,
                conversation_id=conversation.id,
                low_id=conversation.low_id,
                high_id=conversation.high_id,
                created_at=await self.now(),
                result_kind=kind,
                outcome_id=result.id if isinstance(result, StudyOutcomeRevision) else None,
                feedback_id=result.id if isinstance(result, FeedbackRevision) else None,
                feedback_version=result.version if isinstance(result, FeedbackRevision) else None,
                prompt_id=result.id if isinstance(result, StudyPromptReceipt) else None,
            )
        )
        await self.session.flush()

    async def save_study_outcome(self, revision: StudyOutcomeRevision) -> None:
        conversation = self.checked_conversation(revision.actor_id, revision.conversation_id)
        root = await self.session.get(
            StudyOutcomeRecord, (revision.conversation_id, revision.actor_id)
        )
        if root is None:
            root = StudyOutcomeRecord(
                conversation_id=revision.conversation_id,
                actor_id=revision.actor_id,
                low_id=conversation.low_id,
                high_id=conversation.high_id,
                current_version=revision.version,
            )
            self.session.add(root)
            await self.session.flush()
        elif revision.version != root.current_version + 1:
            raise RuntimeError("Study outcome write differs from its actual current revision")
        row = StudyOutcomeRevisionRecord(
            id=revision.id,
            conversation_id=revision.conversation_id,
            actor_id=revision.actor_id,
            low_id=conversation.low_id,
            high_id=conversation.high_id,
            version=revision.version,
            answer=revision.answer.value,
            changed_at=revision.changed_at,
        )
        assign_origin(row)
        self.session.add(row)
        root.current_version = revision.version
        await self.session.flush()
        await self.feedback_recorders.outcome(self.session, revision)

    async def save_feedback(self, revision: FeedbackRevision) -> None:
        conversation = self.checked_conversation(
            revision.reviewer_id, revision.interaction.conversation.id
        )
        root = await self.session.get(PeerFeedbackRecord, revision.id)
        if root is None:
            root = PeerFeedbackRecord(
                id=revision.id,
                conversation_id=conversation.id,
                reviewer_id=revision.reviewer_id,
                partner_id=revision.partner_id,
                low_id=conversation.low_id,
                high_id=conversation.high_id,
                current_version=revision.version,
            )
            self.session.add(root)
            await self.session.flush()
        elif (
            root.reviewer_id != revision.reviewer_id
            or root.partner_id != revision.partner_id
            or revision.version != root.current_version + 1
        ):
            raise RuntimeError(
                "Feedback write differs from its actual ordered pair/current revision"
            )
        row = PeerFeedbackRevisionRecord(
            feedback_id=revision.id,
            version=revision.version,
            conversation_id=conversation.id,
            reviewer_id=revision.reviewer_id,
            partner_id=revision.partner_id,
            low_id=conversation.low_id,
            high_id=conversation.high_id,
            worked_confirmation_id=revision.worked_confirmation.id,
            worked_answer="yes",
            low_message_id=revision.interaction.low_message.id
            if revision.interaction.low_message is not None
            else None,
            high_message_id=revision.interaction.high_message.id
            if revision.interaction.high_message is not None
            else None,
            again=revision.content.again.value,
            descriptors=[value.value for value in revision.content.descriptors],
            team_note=revision.content.team_note,
            changed_at=revision.changed_at,
        )
        assign_origin(row)
        self.session.add(row)
        root.current_version = revision.version
        # Author updates deliberately never assign current_removal_id.
        await self.session.flush()
        await self.feedback_recorders.assessment(self.session, revision)

    async def save_prompt_receipt(self, receipt: StudyPromptReceipt) -> None:
        conversation = self.checked_conversation(receipt.actor_id, receipt.conversation_id)
        row = StudyPromptReceiptRecord(
            id=receipt.id,
            conversation_id=receipt.conversation_id,
            actor_id=receipt.actor_id,
            low_id=conversation.low_id,
            high_id=conversation.high_id,
            offered_at=receipt.offered_at,
        )
        assign_origin(row)
        self.session.add(row)
        await self.session.flush()
        await self.feedback_recorders.prompt(self.session, receipt)


@dataclass(frozen=True, slots=True)
class SqlFeedbackUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorders: FeedbackRecorders

    @asynccontextmanager
    async def transaction(self, conversation_id: UUID) -> AsyncIterator[SqlFeedbackTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlFeedbackTransaction(
                session, conversation_id, record_message_outcome, feedback_recorders=self.recorders
            )
