from dataclasses import dataclass
from uuid import UUID, uuid4

from studymate.application.feedback.intents import (
    FeedbackIntentScope,
    finish_feedback,
    prior_intent,
)
from studymate.application.feedback.ports import (
    FeedbackIntent,
    FeedbackOperation,
    FeedbackUnitOfWork,
    FeedbackVersionConflictError,
    WorkedConfirmationRequiredError,
)
from studymate.application.idempotency import IntentFingerprinter, IntentKey
from studymate.application.identity.sessions import SessionCredential, SessionHasher
from studymate.application.messaging.commands import authorize_conversation
from studymate.domain.feedback.assessments import FeedbackContent, FeedbackRevision
from studymate.domain.feedback.interaction import AcceptedConversationRef
from studymate.domain.feedback.outcomes import StudyAnswer


@dataclass(frozen=True, slots=True)
class SaveFeedbackCommand:
    credential: SessionCredential
    conversation_id: UUID
    content: FeedbackContent
    expected_version: int
    key: IntentKey

    def __post_init__(self) -> None:
        if isinstance(self.expected_version, bool) or self.expected_version < 0:
            raise ValueError("Expected feedback version must be nonnegative")


@dataclass(frozen=True, slots=True)
class SaveFeedback:
    unit_of_work: FeedbackUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(self, command: SaveFeedbackCommand) -> FeedbackRevision:
        async with self.unit_of_work.transaction(command.conversation_id) as transaction:
            actor, access = await authorize_conversation(
                transaction, self.hasher, command.credential, command.conversation_id
            )
            reviewer_id = actor.session.account_id
            partner_id = access.conversation.pair.counterpart(reviewer_id)
            digest = await self.fingerprinter.fingerprint(
                (
                    "feedback.assessment.v1",
                    str(reviewer_id),
                    str(command.conversation_id),
                    command.content.again.value,
                    ",".join(command.content.descriptors),
                    "none"
                    if command.content.team_note is None
                    else "note:" + command.content.team_note,
                    str(command.expected_version),
                )
            )
            scope = FeedbackIntentScope(
                reviewer_id, FeedbackOperation.ASSESSMENT, command.key, digest
            )
            prior = await prior_intent(transaction, scope)
            if prior is not None:
                if (
                    not isinstance(prior.result, FeedbackRevision)
                    or prior.result.reviewer_id != reviewer_id
                    or prior.result.interaction.conversation.id != command.conversation_id
                    or prior.result.partner_id != partner_id
                ):
                    raise RuntimeError("Assessment intent lost its original typed result")
                await finish_feedback(transaction, actor)
                return prior.result
            current = await transaction.current_feedback(reviewer_id, partner_id)
            version = current.revision.version if current is not None else 0
            if current is not None and (
                current.revision.reviewer_id != reviewer_id
                or current.revision.partner_id != partner_id
            ):
                raise RuntimeError("Current assessment belongs to another ordered partner pair")
            if version != command.expected_version:
                raise FeedbackVersionConflictError(version)
            confirmation = await transaction.study_outcome(reviewer_id, command.conversation_id)
            if confirmation is None or confirmation.answer != StudyAnswer.YES:
                raise WorkedConfirmationRequiredError
            interaction = await transaction.interaction(reviewer_id, command.conversation_id)
            if interaction.conversation != AcceptedConversationRef.from_conversation(
                access.conversation
            ):
                raise RuntimeError("Feedback interaction differs from its authorized conversation")
            revision = FeedbackRevision(
                current.revision.id if current is not None else uuid4(),
                version + 1,
                reviewer_id,
                interaction,
                confirmation,
                command.content,
                await transaction.now(),
            )
            await transaction.save_feedback(revision)
            await transaction.remember_feedback_intent(
                reviewer_id, scope.operation, command.key, FeedbackIntent(digest, revision)
            )
            await finish_feedback(transaction, actor)
            return revision
