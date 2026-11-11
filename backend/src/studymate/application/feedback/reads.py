"""Own retained feedback/history reads; no target profile or public aggregate grant."""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from studymate.application.feedback.intents import finish_feedback
from studymate.application.feedback.ports import FeedbackUnitOfWork
from studymate.application.identity.sessions import SessionCredential, SessionHasher
from studymate.application.messaging.commands import authorize_conversation
from studymate.domain.feedback.assessments import CurrentFeedback
from studymate.domain.feedback.interaction import AcceptedConversationRef
from studymate.domain.feedback.outcomes import StudyAnswer, StudyOutcomeRevision


@dataclass(frozen=True, slots=True)
class ReadOwnStudyOutcome:
    unit_of_work: FeedbackUnitOfWork
    hasher: SessionHasher

    async def __call__(
        self, credential: SessionCredential, conversation_id: UUID
    ) -> StudyOutcomeRevision | None:
        async with self.unit_of_work.transaction(conversation_id) as transaction:
            actor, access = await authorize_conversation(
                transaction, self.hasher, credential, conversation_id
            )
            current = await transaction.study_outcome(actor.session.account_id, conversation_id)
            if current is not None and (
                current.actor_id != actor.session.account_id
                or current.conversation_id != conversation_id
                or current.pair != access.conversation.pair
            ):
                raise RuntimeError("Own study outcome projection belongs to another participant")
            await finish_feedback(transaction, actor)
            return current


@dataclass(frozen=True, slots=True)
class ReadOwnFeedback:
    unit_of_work: FeedbackUnitOfWork
    hasher: SessionHasher

    async def __call__(
        self, credential: SessionCredential, conversation_id: UUID
    ) -> CurrentFeedback | None:
        async with self.unit_of_work.transaction(conversation_id) as transaction:
            actor, access = await authorize_conversation(
                transaction, self.hasher, credential, conversation_id
            )
            reviewer_id = actor.session.account_id
            partner_id = access.conversation.pair.counterpart(reviewer_id)
            current = await transaction.current_feedback(reviewer_id, partner_id)
            if current is not None and (
                current.revision.reviewer_id != reviewer_id
                or current.revision.partner_id != partner_id
            ):
                raise RuntimeError(
                    "Own feedback projection belongs to another ordered partner pair"
                )
            await finish_feedback(transaction, actor)
            return current


class FeedbackPublication(StrEnum):
    PRIVATE_ONLY = "private_only"
    ELIGIBLE = "eligible"
    REMOVED = "removed"


@dataclass(frozen=True, slots=True)
class OwnFeedbackContext:
    current: CurrentFeedback | None
    outcome: StudyOutcomeRevision | None
    can_submit: bool
    current_publication: FeedbackPublication | None
    submission_publication: FeedbackPublication | None


@dataclass(frozen=True, slots=True)
class ReadOwnFeedbackContext:
    unit_of_work: FeedbackUnitOfWork
    hasher: SessionHasher

    async def __call__(
        self, credential: SessionCredential, conversation_id: UUID
    ) -> OwnFeedbackContext:
        async with self.unit_of_work.transaction(conversation_id) as transaction:
            actor, access = await authorize_conversation(
                transaction, self.hasher, credential, conversation_id
            )
            reviewer_id = actor.session.account_id
            partner_id = access.conversation.pair.counterpart(reviewer_id)
            current = await transaction.current_feedback(reviewer_id, partner_id)
            outcome = await transaction.study_outcome(reviewer_id, conversation_id)
            interaction = await transaction.interaction(reviewer_id, conversation_id)
            if (
                (
                    current is not None
                    and (
                        current.revision.reviewer_id != reviewer_id
                        or current.revision.partner_id != partner_id
                    )
                )
                or (
                    outcome is not None
                    and (
                        outcome.actor_id != reviewer_id
                        or outcome.conversation_id != conversation_id
                        or outcome.pair != access.conversation.pair
                    )
                )
                or interaction.conversation
                != AcceptedConversationRef.from_conversation(access.conversation)
            ):
                raise RuntimeError(
                    "Feedback context differs from its authorized participant source"
                )
            removed = current is not None and current.removal is not None
            current_publication = (
                None
                if current is None
                else FeedbackPublication.REMOVED
                if removed
                else FeedbackPublication.ELIGIBLE
                if current.revision.aggregate_eligible
                else FeedbackPublication.PRIVATE_ONLY
            )
            can_submit = outcome is not None and outcome.answer == StudyAnswer.YES
            submission_publication = (
                None
                if not can_submit
                else FeedbackPublication.REMOVED
                if removed
                else FeedbackPublication.ELIGIBLE
                if interaction.two_way
                else FeedbackPublication.PRIVATE_ONLY
            )
            await finish_feedback(transaction, actor)
            return OwnFeedbackContext(
                current, outcome, can_submit, current_publication, submission_publication
            )
