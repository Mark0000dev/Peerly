from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.domain.feedback.assessments import StudyAgain
from studymate.domain.feedback.summary import PUBLIC_RESPONSE_THRESHOLD
from studymate.infrastructure.feedback.models import (
    PeerFeedbackRecord,
    PeerFeedbackRemovalRecord,
    PeerFeedbackRevisionRecord,
    StudyOutcomeRevisionRecord,
)
from studymate.infrastructure.feedback.summary import read_feedback_summary
from studymate.infrastructure.persistence.catalogue_models import SubjectRecord
from studymate.infrastructure.persistence.message_models import MessageRecord
from studymate.infrastructure.requests.models import RequestRevisionRecord
from tests.integration.feedback.fixture import FeedbackServices, prepared
from tests.integration.operator.test_reads import operator
from tests.integration.requests.fixture import action, additional_peer, sent
from tests.integration.test_message_commands import Chat

pytestmark = pytest.mark.integration


async def test_sql_summary_counts_current_distinct_all_answers_and_removal_survives_author_edit(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    target = api.chat.recipient
    async with api.chat.api.sessions() as session:
        subject_id = await session.scalar(select(SubjectRecord.id).limit(1))
        assert isinstance(subject_id, UUID)
    services = [api]
    for _ in range(PUBLIC_RESPONSE_THRESHOLD - 1):
        sender = await additional_peer(identity_engine, subject_id)
        request = await sent(api.chat.api, sender, target)
        accepted = await api.chat.api.accept(action(target, sender, request))
        services.append(
            FeedbackServices(Chat(sender, target, api.chat.api, accepted.conversation.id), api.uow)
        )
    for pair, answer in zip(services, StudyAgain, strict=True):
        await pair.exchange()
        await pair.outcomes()(pair.outcome())
        await pair.feedback()(pair.review(again=answer))
    async with api.chat.api.sessions() as session:
        summary = await read_feedback_summary(session, target.id)
        assert summary.responses == PUBLIC_RESPONSE_THRESHOLD
        assert (summary.yes, summary.maybe, summary.no) == (1, 1, 1)
    moderator = await operator(identity_engine)
    own = await api.read_feedback()(api.chat.sender.credential, api.chat.conversation_id)
    assert own is not None
    removal_id = uuid4()
    async with api.chat.api.sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        session.add(
            PeerFeedbackRemovalRecord(
                id=removal_id,
                feedback_id=own.revision.id,
                source_version=own.revision.version,
                operator_id=moderator.id,
                operator_access_version=1,
                operator_access_active=True,
                kind="fraudulent",
                reason="Documented synthetic moderation source",
                removed_at=now,
            )
        )
        await session.flush()
        await session.execute(
            update(PeerFeedbackRecord)
            .where(PeerFeedbackRecord.id == own.revision.id)
            .values(current_removal_id=removal_id)
        )
    second = await api.feedback()(api.review(version=1, again=StudyAgain.NO))
    removed = await api.read_feedback()(api.chat.sender.credential, api.chat.conversation_id)
    assert removed is not None
    assert removed.revision == second
    assert removed.removal is not None
    assert removed.removal.source_version == own.revision.version
    async with api.chat.api.sessions() as session:
        summary = await read_feedback_summary(session, target.id)
        assert summary.building
        assert summary.responses == PUBLIC_RESPONSE_THRESHOLD - 1
        assert (summary.yes, summary.maybe, summary.no) == (None, None, None)
        root = await session.get(PeerFeedbackRecord, second.id)
        assert root is not None
        assert root.current_removal_id == removal_id


@pytest.mark.parametrize(
    "fault", ["low_author", "high_author", "worked_actor", "again", "descriptors", "note"]
)
async def test_database_rejects_forged_sources_or_unbounded_assessment_payload(
    identity_engine: AsyncEngine, fault: str
) -> None:
    api = await prepared(identity_engine)
    await api.exchange()
    yes = await api.outcomes()(api.outcome())
    other_yes = await api.outcomes()(api.outcome(owner=api.chat.recipient))
    first = await api.feedback()(api.review())
    low, high = first.interaction.low_message, first.interaction.high_message
    assert low is not None
    assert high is not None
    row = PeerFeedbackRevisionRecord(
        feedback_id=first.id,
        version=first.version + 1,
        conversation_id=api.chat.conversation_id,
        reviewer_id=api.chat.sender.id,
        partner_id=api.chat.recipient.id,
        low_id=first.interaction.conversation.pair.low,
        high_id=first.interaction.conversation.pair.high,
        worked_confirmation_id=other_yes.id if fault == "worked_actor" else yes.id,
        worked_answer="yes",
        low_message_id=high.id if fault == "low_author" else low.id,
        high_message_id=low.id if fault == "high_author" else high.id,
        again="bad" if fault == "again" else "yes",
        descriptors=["supportive", "supportive"] if fault == "descriptors" else [],
        team_note=" " if fault == "note" else None,
        changed_at=first.changed_at,
    )
    async with api.chat.api.sessions() as session:
        session.add(row)
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()
    async with api.chat.api.sessions() as session:
        assert len(tuple(await session.scalars(select(PeerFeedbackRevisionRecord)))) == 1


async def test_actual_clock_regression_metadata_does_not_erase_committed_message_or_yes_evidence(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    await api.exchange()
    yes = await api.outcomes()(api.outcome())
    async with api.chat.api.sessions.begin() as session:
        accepted = await session.scalar(
            select(RequestRevisionRecord.changed_at).where(
                RequestRevisionRecord.conversation_id == api.chat.conversation_id,
                RequestRevisionRecord.state == "accepted",
            )
        )
        assert isinstance(accepted, datetime)
        # Synthetic retained facts model independent host-clock adjustments.
        await session.execute(
            update(MessageRecord)
            .where(MessageRecord.conversation_id == api.chat.conversation_id)
            .values(sent_at=accepted - timedelta(days=1))
        )
        await session.execute(
            update(StudyOutcomeRevisionRecord)
            .where(StudyOutcomeRevisionRecord.id == yes.id)
            .values(changed_at=accepted - timedelta(hours=1))
        )
    review = await api.feedback()(api.review())
    assert review.aggregate_eligible
    assert review.worked_confirmation.changed_at < review.interaction.accepted_at
    assert review.interaction.low_message is not None
    assert review.interaction.low_message.sent_at < review.interaction.accepted_at
