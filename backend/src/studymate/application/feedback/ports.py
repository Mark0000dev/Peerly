"""Accepted conversation facts and retained feedback writes in one transaction."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from studymate.application.idempotency import IntentKey
from studymate.application.messaging.ports import ConversationAuthority
from studymate.domain.feedback.assessments import CurrentFeedback, FeedbackRevision
from studymate.domain.feedback.interaction import InteractionEvidence
from studymate.domain.feedback.outcomes import StudyOutcomeRevision, StudyPromptReceipt


class FeedbackVersionConflictError(Exception):
    def __init__(self, current_version: int) -> None:
        self.current_version = current_version
        super().__init__("Feedback source version changed")


class WorkedConfirmationRequiredError(Exception):
    pass


class FeedbackOperation(StrEnum):
    STUDY_OUTCOME = "study_outcome"
    ASSESSMENT = "assessment"
    PROMPT_VISIT = "prompt_visit"


@dataclass(frozen=True, slots=True)
class FeedbackIntent:
    fingerprint: bytes = field(repr=False)
    result: StudyOutcomeRevision | FeedbackRevision | StudyPromptReceipt | None = field(repr=False)


class FeedbackTransaction(ConversationAuthority, Protocol):
    async def interaction(self, actor_id: UUID, conversation_id: UUID) -> InteractionEvidence:
        """Actual accepted request time and first intentional human message per participant."""
        ...

    async def study_outcome(
        self, actor_id: UUID, conversation_id: UUID
    ) -> StudyOutcomeRevision | None: ...

    async def current_feedback(
        self, reviewer_id: UUID, partner_id: UUID
    ) -> CurrentFeedback | None: ...

    async def prompt_receipt(
        self, actor_id: UUID, conversation_id: UUID
    ) -> StudyPromptReceipt | None: ...

    async def feedback_intent(
        self, actor_id: UUID, operation: FeedbackOperation, key: IntentKey
    ) -> FeedbackIntent | None: ...

    async def remember_feedback_intent(
        self, actor_id: UUID, operation: FeedbackOperation, key: IntentKey, intent: FeedbackIntent
    ) -> None: ...

    async def save_study_outcome(self, revision: StudyOutcomeRevision) -> None:
        """Append revision/current pointer and mandatory canonical metadata in same transaction."""
        ...

    async def save_feedback(self, revision: FeedbackRevision) -> None:
        """One current ordered reviewer/partner; retain immutable eligibility/history/events.

        Preserve any existing moderator removal and its original source/reason across
        author revisions. An author update cannot clear a removal."""
        ...

    async def save_prompt_receipt(self, receipt: StudyPromptReceipt) -> None:
        """Unique actor/conversation explicit visit receipt; no GET/typing side effect."""
        ...


class FeedbackUnitOfWork(Protocol):
    def transaction(
        self, conversation_id: UUID
    ) -> AbstractAsyncContextManager[FeedbackTransaction]: ...
