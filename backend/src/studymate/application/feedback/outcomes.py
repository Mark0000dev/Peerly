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
)
from studymate.application.idempotency import IntentFingerprinter, IntentKey
from studymate.application.identity.sessions import SessionCredential, SessionHasher
from studymate.application.messaging.commands import authorize_conversation
from studymate.domain.feedback.outcomes import StudyAnswer, StudyOutcomeRevision


@dataclass(frozen=True, slots=True)
class StudyOutcomeCommand:
    credential: SessionCredential
    conversation_id: UUID
    answer: StudyAnswer
    expected_version: int
    key: IntentKey

    def __post_init__(self) -> None:
        if isinstance(self.expected_version, bool) or self.expected_version < 0:
            raise ValueError("Expected study outcome version must be nonnegative")


@dataclass(frozen=True, slots=True)
class SaveStudyOutcome:
    unit_of_work: FeedbackUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(self, command: StudyOutcomeCommand) -> StudyOutcomeRevision:
        async with self.unit_of_work.transaction(command.conversation_id) as transaction:
            actor, access = await authorize_conversation(
                transaction, self.hasher, command.credential, command.conversation_id
            )
            actor_id = actor.session.account_id
            digest = await self.fingerprinter.fingerprint(
                (
                    "feedback.study_outcome.v1",
                    str(actor_id),
                    str(command.conversation_id),
                    command.answer.value,
                    str(command.expected_version),
                )
            )
            scope = FeedbackIntentScope(
                actor_id, FeedbackOperation.STUDY_OUTCOME, command.key, digest
            )
            prior = await prior_intent(transaction, scope)
            if prior is not None:
                if (
                    not isinstance(prior.result, StudyOutcomeRevision)
                    or prior.result.actor_id != actor_id
                    or prior.result.conversation_id != command.conversation_id
                    or prior.result.pair != access.conversation.pair
                ):
                    raise RuntimeError("Study outcome intent lost its original typed result")
                await finish_feedback(transaction, actor)
                return prior.result
            current = await transaction.study_outcome(actor_id, command.conversation_id)
            version = current.version if current is not None else 0
            if current is not None and (
                current.actor_id != actor_id
                or current.conversation_id != command.conversation_id
                or current.pair != access.conversation.pair
            ):
                raise RuntimeError("Study outcome source belongs to another participant")
            if version != command.expected_version:
                raise FeedbackVersionConflictError(version)
            revision = StudyOutcomeRevision(
                uuid4(),
                command.conversation_id,
                access.conversation.pair,
                actor_id,
                version + 1,
                command.answer,
                await transaction.now(),
            )
            await transaction.save_study_outcome(revision)
            await transaction.remember_feedback_intent(
                actor_id, scope.operation, command.key, FeedbackIntent(digest, revision)
            )
            await finish_feedback(transaction, actor)
            return revision
