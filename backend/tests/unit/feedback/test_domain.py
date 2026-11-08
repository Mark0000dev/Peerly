from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from studymate.domain.feedback.analytics import outcome_metrics
from studymate.domain.feedback.assessments import (
    MAX_TEAM_NOTE_LENGTH,
    CurrentFeedback,
    FeedbackContent,
    FeedbackDescriptor,
    FeedbackRemoval,
    RemovalKind,
    StudyAgain,
)
from studymate.domain.feedback.interaction import (
    PROMPT_DELAY,
    AcceptedConversationRef,
    HumanMessageEvidence,
    InteractionEvidence,
)
from studymate.domain.feedback.outcomes import StudyAnswer, StudyOutcomeRevision, StudyPromptReceipt
from studymate.domain.feedback.summary import (
    PUBLIC_RESPONSE_THRESHOLD,
    summarize_feedback,
    summary_from_counts,
)
from studymate.domain.messaging import ChatConversation, ConfirmedMessage, MessageContent
from tests.unit.feedback.fixture import PARTNER, feedback, interaction, outcome
from tests.unit.identity_store import NOW


async def test_actual_human_message_evidence_keeps_ids_not_private_body() -> None:
    source = interaction()
    message = ConfirmedMessage(
        uuid4(),
        uuid4(),
        source.conversation.id,
        source.conversation.pair,
        source.conversation.pair.low,
        uuid4(),
        1,
        MessageContent("private actual text"),
        NOW,
    )
    evidence = HumanMessageEvidence.from_message(message)
    assert evidence.id == message.id
    assert evidence.author_id == message.author_id
    assert "private actual text" not in repr(evidence)


@pytest.mark.parametrize("bad", [True, 0, -1])
def test_human_message_sequence_must_be_real_positive(bad: int) -> None:
    source = interaction()
    assert source.low_message is not None
    with pytest.raises(ValueError, match="actual confirmed sequence"):
        replace(source.low_message, sequence=bad)


@pytest.mark.parametrize("bad", ["conversation", "author", "duplicate_sequence"])
def test_interaction_rejects_mismatched_source(bad: str) -> None:
    source = interaction()
    message = source.low_message
    assert message is not None
    if bad == "conversation":
        message = replace(message, conversation_id=uuid4())
    elif bad == "author":
        message = replace(message, author_id=source.conversation.pair.high)
    else:
        assert source.high_message is not None
        message = replace(message, sequence=source.high_message.sequence)
    with pytest.raises(ValueError, match=r"evidence|Two-way"):
        replace(source, low_message=message)


def test_prompt_fixed24h_boundary_and_actual_exchange_without_typing_or_get() -> None:
    source = interaction()
    at = source.accepted_at + PROMPT_DELAY
    assert not source.prompt_available(at - timedelta(microseconds=1))
    assert source.prompt_available(at)
    assert not replace(source, high_message=None).prompt_available(at)
    assert source.high_message is not None
    future = replace(
        source, high_message=replace(source.high_message, sent_at=at + timedelta(seconds=1))
    )
    assert future.prompt_available(at)
    assert future.prompt_available(at + timedelta(seconds=1))


@pytest.mark.parametrize("version", [True, 0, -1])
def test_outcome_and_feedback_require_real_revision(version: int) -> None:
    source = interaction()
    with pytest.raises(ValueError, match="revision must be positive"):
        replace(outcome(source), version=version)
    with pytest.raises(ValueError, match="revision must be positive"):
        replace(feedback(), version=version)


@pytest.mark.parametrize("fault", ["actor", "not_yet", "did_not_work_out", "convo", "pair"])
def test_feedback_requires_actual_owned_explicit_worked_confirmation(fault: str) -> None:
    review = feedback()
    answer = review.worked_confirmation
    if fault == "actor":
        answer = replace(answer, actor_id=review.partner_id)
    elif fault in {"not_yet", "did_not_work_out"}:
        answer = replace(answer, answer=StudyAnswer(fault))
    elif fault == "convo":
        answer = replace(answer, conversation_id=uuid4())
    elif fault == "pair":
        answer = outcome(interaction(UUID(int=90)), actor=UUID(int=90))
    elif fault == "future":
        answer = replace(answer, changed_at=review.changed_at + timedelta(seconds=1))
    else:
        answer = replace(answer, changed_at=review.interaction.accepted_at - timedelta(seconds=1))
    with pytest.raises(ValueError, match="explicit worked-Yes"):
        replace(review, worked_confirmation=answer)


def test_feedback_rejects_foreign_reviewer_but_preserves_clock_regressed_metadata() -> None:
    review = feedback()
    with pytest.raises(ValueError, match="participant"):
        replace(review, reviewer_id=uuid4())
    assert review.interaction.high_message is not None
    source = replace(
        review.interaction,
        low_message=replace(
            review.interaction.low_message,
            sent_at=review.interaction.accepted_at - timedelta(days=1),
        )
        if review.interaction.low_message is not None
        else None,
        high_message=replace(review.interaction.high_message, sent_at=NOW + timedelta(days=1)),
    )
    historical = replace(
        review,
        interaction=source,
        worked_confirmation=replace(
            review.worked_confirmation,
            changed_at=review.interaction.accepted_at - timedelta(days=1),
        ),
        changed_at=review.interaction.accepted_at - timedelta(days=2),
    )
    assert historical.aggregate_eligible
    assert historical.worked_confirmation.changed_at < historical.interaction.accepted_at
    removal = FeedbackRemoval(
        historical.id,
        historical.version,
        uuid4(),
        RemovalKind.ABUSIVE,
        "Actual prior source",
        historical.changed_at - timedelta(hours=1),
    )
    assert CurrentFeedback(historical, removal).removal == removal


def test_private_note_and_descriptors_are_bounded_not_public_text() -> None:
    content = FeedbackContent(
        StudyAgain.NO,
        (FeedbackDescriptor.SUPPORTIVE, FeedbackDescriptor.PREPARED),
        "  private team note\ntext  ",
    )
    assert content.descriptors == (FeedbackDescriptor.PREPARED, FeedbackDescriptor.SUPPORTIVE)
    assert content.team_note == "private team note\ntext"
    assert "private team note" not in repr(content)
    assert FeedbackContent(StudyAgain.MAYBE, team_note="  ").team_note is None
    with pytest.raises(ValueError, match="distinct known"):
        FeedbackContent(StudyAgain.YES, (FeedbackDescriptor.PREPARED,) * 2)
    with pytest.raises(ValueError, match="Text length"):
        FeedbackContent(StudyAgain.YES, team_note="x" * (MAX_TEAM_NOTE_LENGTH + 1))


def test_private_offplatform_never_promotes_when_new_evidence_appears() -> None:
    private = feedback(two_way=False)
    assert not private.aggregate_eligible
    assert summarize_feedback(PARTNER, (CurrentFeedback(private),)).responses == 0
    # A new explicit revision may capture later actual exchange; the original stays immutable.
    assert private.interaction.low_message is not None
    fresh_message = HumanMessageEvidence(
        uuid4(),
        private.interaction.conversation.id,
        private.partner_id,
        2,
        NOW - timedelta(minutes=1),
    )
    public = replace(
        private, version=2, interaction=replace(private.interaction, high_message=fresh_message)
    )
    assert public.aggregate_eligible
    assert not private.aggregate_eligible


def test_summary_denominator_includes_all_three_and_updates_removal_retracts_threshold() -> None:
    records = tuple(
        CurrentFeedback(feedback(UUID(int=100 + i), again=answer))
        for i, answer in enumerate(StudyAgain)
    )
    summary = summarize_feedback(PARTNER, records)
    assert summary.responses == PUBLIC_RESPONSE_THRESHOLD
    assert (summary.yes, summary.maybe, summary.no) == (1, 1, 1)
    assert not summary.building
    removal = FeedbackRemoval(
        records[0].revision.id,
        1,
        uuid4(),
        RemovalKind.FRAUDULENT,
        "Documented synthetic evidence",
        NOW,
    )
    revised = (replace(records[0], removal=removal), *records[1:])
    hidden = summarize_feedback(PARTNER, revised)
    assert hidden.building
    assert hidden.responses == PUBLIC_RESPONSE_THRESHOLD - 1
    assert (hidden.yes, hidden.maybe, hidden.no) == (None, None, None)
    updated = replace(records[0].revision, version=2, content=FeedbackContent(StudyAgain.NO))
    summary2 = summarize_feedback(PARTNER, (CurrentFeedback(updated), *records[1:]))
    assert summary2.responses == PUBLIC_RESPONSE_THRESHOLD
    assert summary2.no == PUBLIC_RESPONSE_THRESHOLD - 1


def test_summary_rejects_duplicate_or_other_target_not_fabricates_partners() -> None:
    review = CurrentFeedback(feedback())
    with pytest.raises(ValueError, match="distinct partner"):
        summarize_feedback(PARTNER, (review, review))
    with pytest.raises(ValueError, match="distinct partner"):
        summarize_feedback(uuid4(), (review,))


@pytest.mark.parametrize("fault", ["version", "reason", "source"])
def test_removal_requires_documented_current_source(fault: str) -> None:
    review = feedback()
    removal = FeedbackRemoval(review.id, 1, uuid4(), RemovalKind.ABUSIVE, "actual reason", NOW)
    if fault == "version":
        with pytest.raises(ValueError, match="actual feedback source"):
            replace(removal, source_version=0)
    elif fault == "reason":
        with pytest.raises(ValueError, match="Text length"):
            replace(removal, reason=" ")
    else:
        removal = replace(removal, assessment_id=uuid4())
        with pytest.raises(ValueError, match="moderation source"):
            CurrentFeedback(review, removal)


def test_outcome_metrics_latest_in_window_paironce_and_unknown_is_not_failure() -> None:
    first, second, unknown = (
        interaction(UUID(int=100)),
        interaction(UUID(int=101)),
        interaction(UUID(int=102)),
    )
    latest = replace(outcome(first), version=2, answer=StudyAnswer.NOT_YET)
    answers = (
        outcome(first),
        latest,
        outcome(first, actor=PARTNER),
        outcome(second, answer=StudyAnswer.NOT_YET),
        replace(outcome(unknown), changed_at=NOW + timedelta(hours=1)),
    )
    metrics = outcome_metrics((first, second, unknown), answers, NOW - timedelta(days=1), NOW)
    assert metrics.accepted_pairs == PUBLIC_RESPONSE_THRESHOLD
    assert metrics.responding_pairs == PUBLIC_RESPONSE_THRESHOLD - 1
    assert metrics.started_pairs == 1
    assert metrics.conflicting_pairs == 1
    assert metrics.response_coverage == pytest.approx(2 / 3)
    assert metrics.started_share_among_responding == pytest.approx(1 / 2)
    empty = outcome_metrics((), (), NOW - timedelta(days=1), NOW)
    assert empty.response_coverage is None
    assert empty.started_share_among_responding is None


@pytest.mark.parametrize(
    "fault",
    ["window", "duplicate", "future_accept", "foreign", "conflicting_version"],
)
def test_metrics_reject_invalid_cohort_or_answer_provenance(fault: str) -> None:
    source = interaction()
    answers: tuple[StudyOutcomeRevision, ...] = (outcome(source),)
    cohort: tuple[InteractionEvidence, ...] = (source,)
    start = NOW - timedelta(days=1)
    if fault == "window":
        start = NOW
    elif fault == "duplicate":
        cohort = (source, source)
    elif fault == "future_accept":
        cohort = (replace(source, accepted_at=NOW, low_message=None, high_message=None),)
    elif fault == "foreign":
        answers = (replace(answers[0], conversation_id=uuid4()),)
    else:
        answers += (replace(answers[0], answer=StudyAnswer.NOT_YET),)
    with pytest.raises(
        ValueError, match=r"observation window|cohort|accepted-pair|conflicting immutable"
    ):
        outcome_metrics(cohort, answers, start, NOW)


def test_prompt_receipt_requires_aware_server_timestamp() -> None:
    receipt = StudyPromptReceipt(uuid4(), uuid4(), uuid4(), NOW)
    with pytest.raises(ValueError, match="timezone"):
        replace(receipt, offered_at=NOW.replace(tzinfo=None))


@pytest.mark.parametrize("version", [True, 0, 1])
def test_immutable_conversation_reference_requires_actual_accepted_revision(version: int) -> None:
    with pytest.raises(ValueError, match="actual accepted"):
        replace(interaction().conversation, accepted_request_version=version)


def test_later_chat_traffic_does_not_change_historical_feedback_evidence() -> None:
    source = interaction()
    ref = source.conversation
    current = ChatConversation(
        ref.id, ref.relationship_id, ref.pair, ref.request_id, ref.accepted_request_version, 3
    )
    later = replace(current, next_message_sequence=100)
    reconstructed = InteractionEvidence.from_conversation(
        later, source.accepted_at, source.low_message, source.high_message
    )
    assert reconstructed == source
    assert AcceptedConversationRef.from_conversation(
        current
    ) == AcceptedConversationRef.from_conversation(later)
    assert "next_message_sequence" not in repr(reconstructed)
    assert source.high_message is not None
    with pytest.raises(ValueError, match="actual committed conversation sequence"):
        InteractionEvidence.from_conversation(
            current,
            source.accepted_at,
            source.low_message,
            replace(source.high_message, sequence=current.next_message_sequence),
        )


@pytest.mark.parametrize("bad", [True, -1])
def test_aggregate_count_source_rejects_non_counts(bad: int) -> None:
    with pytest.raises(ValueError, match="nonnegative integers"):
        summary_from_counts(bad, 0, 0)
