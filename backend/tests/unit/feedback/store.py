from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from uuid import UUID

from studymate.application.errors import StorageUnavailableError
from studymate.application.feedback.ports import FeedbackIntent, FeedbackOperation
from studymate.application.idempotency import IntentKey
from studymate.application.messaging.ports import ConversationAccess
from studymate.domain.feedback.assessments import CurrentFeedback, FeedbackRevision
from studymate.domain.feedback.interaction import InteractionEvidence
from studymate.domain.feedback.outcomes import StudyOutcomeRevision, StudyPromptReceipt
from studymate.domain.messaging import ChatConversation
from tests.unit.feedback.fixture import interaction
from tests.unit.identity_store import IdentityStore


class Store(IdentityStore):
    def __init__(self) -> None:
        super().__init__()
        self.actor = replace(self.actor, activation_complete=True)
        self.source = interaction(self.actor.session.account_id)
        reference = self.source.conversation
        conversation = ChatConversation(
            reference.id,
            reference.relationship_id,
            reference.pair,
            reference.request_id,
            reference.accepted_request_version,
            3,
        )
        self.access: ConversationAccess | None = ConversationAccess(
            conversation, True, False, False, False
        )
        self.outcomes: dict[tuple[UUID, UUID], StudyOutcomeRevision] = {}
        self.assessments: dict[tuple[UUID, UUID], CurrentFeedback] = {}
        self.prompts: dict[tuple[UUID, UUID], StudyPromptReceipt] = {}
        self.intents: dict[tuple[UUID, FeedbackOperation, str], FeedbackIntent] = {}
        self.outcome_history: list[StudyOutcomeRevision] = []
        self.feedback_history: list[FeedbackRevision] = []
        self.fail_save = False
        self.expire_on_save = False
        self.source_queries = 0

    @asynccontextmanager
    async def transaction(self, conversation_id: UUID) -> AsyncIterator["Store"]:
        assert conversation_id == self.source.conversation.id
        original = (
            self.outcomes.copy(),
            self.assessments.copy(),
            self.prompts.copy(),
            self.intents.copy(),
            self.outcome_history.copy(),
            self.feedback_history.copy(),
        )
        try:
            yield self
        except BaseException:
            (
                self.outcomes,
                self.assessments,
                self.prompts,
                self.intents,
                self.outcome_history,
                self.feedback_history,
            ) = original
            raise

    async def conversation(
        self, actor_id: UUID, conversation_id: UUID
    ) -> ConversationAccess | None:
        assert actor_id == self.actor.session.account_id
        assert conversation_id == self.source.conversation.id
        return self.access

    async def interaction(self, actor_id: UUID, conversation_id: UUID) -> InteractionEvidence:
        assert actor_id == self.actor.session.account_id
        assert conversation_id == self.source.conversation.id
        self.source_queries += 1
        return self.source

    async def study_outcome(
        self, actor_id: UUID, conversation_id: UUID
    ) -> StudyOutcomeRevision | None:
        return self.outcomes.get((actor_id, conversation_id))

    async def current_feedback(self, reviewer_id: UUID, partner_id: UUID) -> CurrentFeedback | None:
        return self.assessments.get((reviewer_id, partner_id))

    async def prompt_receipt(
        self, actor_id: UUID, conversation_id: UUID
    ) -> StudyPromptReceipt | None:
        return self.prompts.get((actor_id, conversation_id))

    async def feedback_intent(
        self, actor_id: UUID, operation: FeedbackOperation, key: IntentKey
    ) -> FeedbackIntent | None:
        return self.intents.get((actor_id, operation, key.value))

    async def remember_feedback_intent(
        self, actor_id: UUID, operation: FeedbackOperation, key: IntentKey, intent: FeedbackIntent
    ) -> None:
        self.intents[actor_id, operation, key.value] = intent
        if self.fail_save:
            raise StorageUnavailableError
        if self.expire_on_save:
            self.clock = self.actor.session.expires_at

    async def save_study_outcome(self, revision: StudyOutcomeRevision) -> None:
        self.outcomes[revision.actor_id, revision.conversation_id] = revision
        self.outcome_history.append(revision)

    async def save_feedback(self, revision: FeedbackRevision) -> None:
        previous = self.assessments.get((revision.reviewer_id, revision.partner_id))
        self.assessments[revision.reviewer_id, revision.partner_id] = CurrentFeedback(
            revision, previous.removal if previous is not None else None
        )
        self.feedback_history.append(revision)

    async def save_prompt_receipt(self, receipt: StudyPromptReceipt) -> None:
        self.prompts[receipt.actor_id, receipt.conversation_id] = receipt
