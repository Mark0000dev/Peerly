from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest

from studymate.domain.ai.jobs import AiJob, Failure, JobState, Versions
from studymate.domain.ai.tasks import ClarifyGoal, Priority, ReportTriage, Source, TriageReport
from studymate.domain.operator.report_triage import observe_report_triage
from tests.unit.identity_store import NOW


def job() -> AiJob:
    return AiJob(
        uuid4(),
        uuid4(),
        TriageReport(Source(uuid4(), 1), "Actual stored report text"),
        b"d" * 32,
        Versions("controlled-model"),
        NOW,
        NOW + timedelta(minutes=30),
        NOW,
    )


@pytest.mark.parametrize(
    "state",
    [JobState.QUEUED, JobState.RUNNING, JobState.FAILED, JobState.CANCELLED, JobState.EXPIRED],
)
def test_incomplete_or_failed_triage_never_invents_an_advisory_result(state: JobState) -> None:
    actual = replace(job(), state=state)
    observed = observe_report_triage(uuid4(), actual, source_current=True)
    assert observed.state == actual.state
    assert observed.priority is None
    assert observed.rationale is None


def test_stale_suggestion_is_hidden_without_rewriting_actual_completed_job() -> None:
    original = replace(
        job(),
        state=JobState.SUCCEEDED,
        result=ReportTriage(Priority.HIGH, "Private advisory rationale"),
    )
    current = observe_report_triage(uuid4(), original, source_current=True)
    assert current.priority == Priority.HIGH
    assert current.rationale == "Private advisory rationale"
    assert "Private advisory" not in repr(current)
    stale = observe_report_triage(current.report_id, original, source_current=False)
    assert stale.state == JobState.SUCCEEDED
    assert stale.source_current is False
    assert stale.priority is None
    assert stale.rationale is None
    assert original.result is not None


def test_failure_keeps_actual_reason_without_inventing_pending_retry() -> None:
    original = replace(job(), state=JobState.FAILED, failure=Failure.STALE_SOURCE)
    observed = observe_report_triage(uuid4(), original, source_current=False)
    assert observed.failure == Failure.STALE_SOURCE
    assert observed.state == JobState.FAILED


def test_student_ai_task_cannot_be_reinterpreted_as_report_advice() -> None:
    original = replace(job(), task=ClarifyGoal(Source(uuid4(), 1), "Goal context"))
    with pytest.raises(ValueError, match="internal typed report task"):
        observe_report_triage(uuid4(), original, source_current=True)
