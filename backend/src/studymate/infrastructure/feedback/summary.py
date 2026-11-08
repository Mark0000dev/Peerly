"""Bounded count projection; caller must apply the actual People disclosure guard."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.domain.feedback.assessments import StudyAgain
from studymate.domain.feedback.summary import FeedbackSummary, summary_from_counts
from studymate.infrastructure.feedback.models import PeerFeedbackRecord, PeerFeedbackRevisionRecord


async def read_feedback_summary(session: AsyncSession, partner_id: UUID) -> FeedbackSummary:
    # One root per ordered reviewer/partner, only its current revision; never private notes/history.
    rows = (
        await session.execute(
            select(PeerFeedbackRevisionRecord.again, func.count(PeerFeedbackRecord.reviewer_id))
            .join(
                PeerFeedbackRecord,
                (PeerFeedbackRecord.id == PeerFeedbackRevisionRecord.feedback_id)
                & (PeerFeedbackRecord.current_version == PeerFeedbackRevisionRecord.version),
            )
            .where(
                PeerFeedbackRecord.partner_id == partner_id,
                PeerFeedbackRecord.current_removal_id.is_(None),
                PeerFeedbackRevisionRecord.low_message_id.is_not(None),
                PeerFeedbackRevisionRecord.high_message_id.is_not(None),
            )
            .group_by(PeerFeedbackRevisionRecord.again)
        )
    ).all()
    counts = {StudyAgain(row[0]): row[1] for row in rows}
    return summary_from_counts(
        counts.get(StudyAgain.YES, 0), counts.get(StudyAgain.MAYBE, 0), counts.get(StudyAgain.NO, 0)
    )
