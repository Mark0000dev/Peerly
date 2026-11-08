"""Pure counts only; this module grants no profile or aggregate disclosure access."""

from dataclasses import dataclass
from uuid import UUID

from studymate.domain.feedback.assessments import CurrentFeedback, StudyAgain

PUBLIC_RESPONSE_THRESHOLD = 3


@dataclass(frozen=True, slots=True)
class FeedbackSummary:
    responses: int
    yes: int | None
    maybe: int | None
    no: int | None

    @property
    def building(self) -> bool:
        return self.responses < PUBLIC_RESPONSE_THRESHOLD


def summarize_feedback(partner_id: UUID, records: tuple[CurrentFeedback, ...]) -> FeedbackSummary:
    seen: set[UUID] = set()
    counts = dict.fromkeys(StudyAgain, 0)
    for current in records:
        revision = current.revision
        if revision.partner_id != partner_id or revision.reviewer_id in seen:
            raise ValueError("Summary requires one actual current assessment per distinct partner")
        seen.add(revision.reviewer_id)
        if current.removal is None and revision.aggregate_eligible:
            counts[revision.content.again] += 1
    return summary_from_counts(
        counts[StudyAgain.YES], counts[StudyAgain.MAYBE], counts[StudyAgain.NO]
    )


def summary_from_counts(yes: int, maybe: int, no: int) -> FeedbackSummary:
    if any(isinstance(value, bool) or value < 0 for value in (yes, maybe, no)):
        raise ValueError("Feedback summary counts must be nonnegative integers")
    total = yes + maybe + no
    return (
        FeedbackSummary(total, yes, maybe, no)
        if total >= PUBLIC_RESPONSE_THRESHOLD
        else FeedbackSummary(total, None, None, None)
    )
