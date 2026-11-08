"""Self-reported pair outcomes inside an explicit observation window/cohort."""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID

from studymate.domain.feedback.interaction import InteractionEvidence
from studymate.domain.feedback.outcomes import StudyAnswer, StudyOutcomeRevision
from studymate.domain.time import require_aware


@dataclass(frozen=True, slots=True)
class OutcomeMetrics:
    accepted_pairs: int
    responding_pairs: int
    started_pairs: int
    conflicting_pairs: int

    @property
    def response_coverage(self) -> float | None:
        return self.responding_pairs / self.accepted_pairs if self.accepted_pairs else None

    @property
    def started_share_among_responding(self) -> float | None:
        return self.started_pairs / self.responding_pairs if self.responding_pairs else None


def outcome_metrics(
    cohort: tuple[InteractionEvidence, ...],
    answers: tuple[StudyOutcomeRevision, ...],
    window_start: datetime,
    window_end: datetime,
) -> OutcomeMetrics:
    require_aware(window_start)
    require_aware(window_end)
    if window_start >= window_end:
        raise ValueError("Study outcome observation window must be nonempty")
    conversations = {source.conversation.id: source for source in cohort}
    pairs = {source.conversation.pair for source in cohort}
    if len(conversations) != len(cohort) or len(pairs) != len(cohort):
        raise ValueError("Accepted cohort must count each actual conversation pair once")
    if any(source.accepted_at >= window_end for source in cohort):
        raise ValueError("Accepted cohort includes a conversation after the observation window")
    latest: dict[tuple[UUID, UUID], StudyOutcomeRevision] = {}
    for answer in answers:
        source = conversations.get(answer.conversation_id)
        if source is None or source.conversation.pair != answer.pair:
            raise ValueError("Study outcome lies outside its actual accepted-pair source")
        if window_start <= answer.changed_at < window_end:
            key = answer.conversation_id, answer.actor_id
            previous = latest.get(key)
            if previous is not None and previous.version == answer.version and previous != answer:
                raise ValueError("Study outcome revision has conflicting immutable sources")
            if previous is None or answer.version > previous.version:
                latest[key] = answer
    responding = started = conflicting = 0
    for conversation in conversations.values():
        values = {
            answer.answer
            for (conversation_id, _), answer in latest.items()
            if conversation_id == conversation.conversation.id
        }
        responding += bool(values)
        started += StudyAnswer.YES in values
        conflicting += len(values) > 1
    return OutcomeMetrics(len(cohort), responding, started, conflicting)
