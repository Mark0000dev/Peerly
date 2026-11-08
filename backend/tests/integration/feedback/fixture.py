from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.feedback.assessments import SaveFeedback, SaveFeedbackCommand
from studymate.application.feedback.outcomes import SaveStudyOutcome, StudyOutcomeCommand
from studymate.application.feedback.prompts import OfferStudyPromptOnVisit, StudyPromptVisitCommand
from studymate.application.feedback.reads import ReadOwnFeedback, ReadOwnStudyOutcome
from studymate.application.idempotency import IntentKey
from studymate.domain.feedback.assessments import FeedbackContent, StudyAgain
from studymate.domain.feedback.outcomes import StudyAnswer
from studymate.infrastructure.feedback.transactions import FeedbackRecorders, SqlFeedbackUnitOfWork
from studymate.infrastructure.persistence.product_events import (
    record_peer_feedback,
    record_study_outcome,
    record_study_prompt,
)
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.student_actor import Actor
from tests.integration.test_message_commands import Chat, chat

RECORDERS = FeedbackRecorders(record_study_outcome, record_peer_feedback, record_study_prompt)


@dataclass(frozen=True, slots=True)
class FeedbackServices:
    chat: Chat
    uow: SqlFeedbackUnitOfWork

    def outcomes(self) -> SaveStudyOutcome:
        return SaveStudyOutcome(self.uow, HASHER, FINGERPRINTER)

    def feedback(self) -> SaveFeedback:
        return SaveFeedback(self.uow, HASHER, FINGERPRINTER)

    def prompts(self) -> OfferStudyPromptOnVisit:
        return OfferStudyPromptOnVisit(self.uow, HASHER, FINGERPRINTER)

    def read_outcome(self) -> ReadOwnStudyOutcome:
        return ReadOwnStudyOutcome(self.uow, HASHER)

    def read_feedback(self) -> ReadOwnFeedback:
        return ReadOwnFeedback(self.uow, HASHER)

    def outcome(
        self, *, owner: Actor | None = None, version: int = 0, answer: StudyAnswer = StudyAnswer.YES
    ) -> StudyOutcomeCommand:
        return StudyOutcomeCommand(
            (owner if owner is not None else self.chat.sender).credential,
            self.chat.conversation_id,
            answer,
            version,
            IntentKey(str(uuid4())),
        )

    def review(
        self, *, owner: Actor | None = None, version: int = 0, again: StudyAgain = StudyAgain.YES
    ) -> SaveFeedbackCommand:
        return SaveFeedbackCommand(
            (owner if owner is not None else self.chat.sender).credential,
            self.chat.conversation_id,
            FeedbackContent(again, team_note="Synthetic private team note"),
            version,
            IntentKey(str(uuid4())),
        )

    def visit(self) -> StudyPromptVisitCommand:
        return StudyPromptVisitCommand(
            self.chat.sender.credential, self.chat.conversation_id, IntentKey(str(uuid4()))
        )

    async def exchange(self) -> None:
        await self.chat.send()(self.chat.command())
        await self.chat.send()(self.chat.command(self.chat.recipient))


async def prepared(engine: AsyncEngine) -> FeedbackServices:
    return FeedbackServices(
        await chat(engine),
        SqlFeedbackUnitOfWork(async_sessionmaker(engine, expire_on_commit=False), RECORDERS),
    )
