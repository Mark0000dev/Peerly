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
)
from studymate.application.idempotency import IntentFingerprinter, IntentKey
from studymate.application.identity.sessions import SessionCredential, SessionHasher
from studymate.application.messaging.commands import authorize_conversation
from studymate.domain.feedback.interaction import AcceptedConversationRef
from studymate.domain.feedback.outcomes import StudyPromptReceipt


@dataclass(frozen=True, slots=True)
class StudyPromptVisitCommand:
    credential: SessionCredential
    conversation_id: UUID
    key: IntentKey


@dataclass(frozen=True, slots=True)
class OfferStudyPromptOnVisit:
    unit_of_work: FeedbackUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(self, command: StudyPromptVisitCommand) -> StudyPromptReceipt | None:
        async with self.unit_of_work.transaction(command.conversation_id) as transaction:
            actor, access = await authorize_conversation(
                transaction, self.hasher, command.credential, command.conversation_id
            )
            actor_id = actor.session.account_id
            digest = await self.fingerprinter.fingerprint(
                ("feedback.prompt_visit.v1", str(actor_id), str(command.conversation_id))
            )
            scope = FeedbackIntentScope(
                actor_id, FeedbackOperation.PROMPT_VISIT, command.key, digest
            )
            prior = await prior_intent(transaction, scope)
            if prior is not None:
                if prior.result is not None and (
                    not isinstance(prior.result, StudyPromptReceipt)
                    or prior.result.actor_id != actor_id
                    or prior.result.conversation_id != command.conversation_id
                ):
                    raise RuntimeError("Study prompt intent lost its original typed result")
                await finish_feedback(transaction, actor)
                return prior.result
            original = await transaction.prompt_receipt(actor_id, command.conversation_id)
            if original is not None and (
                original.actor_id != actor_id or original.conversation_id != command.conversation_id
            ):
                raise RuntimeError("Study prompt receipt belongs to another participant")
            interaction = await transaction.interaction(actor_id, command.conversation_id)
            if interaction.conversation != AcceptedConversationRef.from_conversation(
                access.conversation
            ):
                raise RuntimeError(
                    "Study prompt interaction differs from its authorized conversation"
                )
            now = await transaction.now()
            receipt: StudyPromptReceipt | None = None
            if (
                original is None
                and interaction.prompt_available(now)
                and await transaction.study_outcome(actor_id, command.conversation_id) is None
            ):
                receipt = StudyPromptReceipt(uuid4(), command.conversation_id, actor_id, now)
                await transaction.save_prompt_receipt(receipt)
            await transaction.remember_feedback_intent(
                actor_id, scope.operation, command.key, FeedbackIntent(digest, receipt)
            )
            await finish_feedback(transaction, actor)
            return receipt
