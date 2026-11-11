from datetime import timedelta
from uuid import UUID, uuid4

from studymate.domain.feedback.assessments import FeedbackContent, FeedbackRevision, StudyAgain
from studymate.domain.feedback.interaction import HumanMessageEvidence, InteractionEvidence
from studymate.domain.feedback.outcomes import StudyAnswer, StudyOutcomeRevision
from studymate.domain.messaging import ChatConversation
from studymate.domain.relationships import AccountPair
from tests.unit.identity_store import NOW

PARTNER = UUID(int=900)
REVIEWER = UUID(int=100)


def interaction(reviewer: UUID = REVIEWER, *, two_way: bool = True) -> InteractionEvidence:
    pair = AccountPair.between(reviewer, PARTNER)
    conversation = ChatConversation(uuid4(), uuid4(), pair, uuid4(), 2, 3)
    accepted = NOW - timedelta(days=2)
    return InteractionEvidence.from_conversation(
        conversation,
        accepted,
        HumanMessageEvidence(uuid4(), conversation.id, pair.low, 1, accepted + timedelta(hours=1)),
        HumanMessageEvidence(uuid4(), conversation.id, pair.high, 2, accepted + timedelta(hours=2))
        if two_way
        else None,
    )


def outcome(
    source: InteractionEvidence,
    *,
    actor: UUID | None = None,
    version: int = 1,
    answer: StudyAnswer = StudyAnswer.YES,
) -> StudyOutcomeRevision:
    return StudyOutcomeRevision(
        uuid4(),
        source.conversation.id,
        source.conversation.pair,
        source.conversation.pair.low if actor is None else actor,
        version,
        answer,
        NOW - timedelta(hours=1),
    )


def feedback(
    reviewer: UUID = REVIEWER, *, again: StudyAgain = StudyAgain.YES, two_way: bool = True
) -> FeedbackRevision:
    source = interaction(reviewer, two_way=two_way)
    return FeedbackRevision(
        uuid4(), 1, reviewer, source, outcome(source, actor=reviewer), FeedbackContent(again), NOW
    )
