from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest

from studymate.application.ai.policy import AdmissionPolicy
from studymate.application.ai.ports import StudentSubmission
from studymate.domain.ai.jobs import AiJob, Failure, JobState, Versions
from studymate.domain.ai.tasks import (
    AiKind,
    AiResult,
    AiTask,
    AssessPhoto,
    Candidate,
    ClarifiedGoal,
    ClarifyGoal,
    Observation,
    PhotoAssessment,
    Priority,
    ReportTriage,
    Source,
    SubjectSuggestions,
    SuggestSubject,
    TriageReport,
    kind_of,
    validate_result,
)
from studymate.domain.media import MediaObjectKind, MediaObjectRef
from studymate.infrastructure.ai.codec import TASK_CODEC, decode_result, output_model

if TYPE_CHECKING:
    from collections.abc import Callable

VALIDATION_ERRORS = (
    r"revision|Text|conform|exceeds|distinct|bounded|versions|digest|deadline|"
    r"Attempt|successful|due|Retry|Internal|required|accept"
)

NOW = datetime(2026, 11, 7, tzinfo=UTC)
SOURCE = Source(UUID(int=1), 1)


def job() -> AiJob:
    return AiJob(
        uuid4(),
        uuid4(),
        ClarifyGoal(SOURCE, "Synthetic goal"),
        b"x" * 32,
        Versions("configured-synthetic-model"),
        NOW,
        NOW + timedelta(minutes=5),
        NOW,
    )


@pytest.mark.parametrize("version", [0, -1, True])
def test_source_requires_real_revision(version: int) -> None:
    with pytest.raises(
        ValueError,
        match=VALIDATION_ERRORS,
    ):
        Source(uuid4(), version)


@pytest.mark.parametrize("text", ["", " ", "x" * 241, "private\x00value", "\ud800"])
def test_explicit_text_is_bounded_and_safe(text: str) -> None:
    with pytest.raises(
        ValueError,
        match=VALIDATION_ERRORS,
    ):
        ClarifyGoal(SOURCE, text)


def test_every_kind_roundtrips_and_schema_forbids_extra_product_actions() -> None:
    tasks: tuple[AiTask, ...] = (
        ClarifyGoal(SOURCE, "Synthetic"),
        SuggestSubject(SOURCE, "Synthetic", (Candidate(uuid4(), "Synthetic candidate"),)),
        AssessPhoto(SOURCE, MediaObjectRef(uuid4(), MediaObjectKind.DISPLAY, uuid4())),
        TriageReport(SOURCE, "Synthetic selected evidence"),
    )
    results: tuple[AiResult, ...] = (
        ClarifiedGoal("Editable suggestion"),
        SubjectSuggestions(()),
        PhotoAssessment(Observation.UNCERTAIN, Observation.YES, Observation.NO),
        ReportTriage(Priority.NORMAL, "Human review required"),
    )
    assert {kind_of(task) for task in tasks} == set(AiKind)
    for task, result in zip(tasks, results, strict=True):
        assert TASK_CODEC.validate_json(TASK_CODEC.dump_json(task)) == task
        validate_result(task, result)
        assert output_model(task).model_json_schema()["additionalProperties"] is False
        assert "Synthetic" not in repr(task)
        with pytest.raises(
            ValueError,
            match=VALIDATION_ERRORS,
        ):
            validate_result(
                task,
                ClarifiedGoal("Wrong schema")
                if not isinstance(task, ClarifyGoal)
                else SubjectSuggestions(()),
            )


@pytest.mark.parametrize(
    "raw",
    [
        b"{}",
        b'{"suggestion":42}',
        b'{"suggestion":"ok","send":true}',
        b"null",
        b"x" * 16385,
        b'{"suggestion":""}',
        b'{"suggestion":"private\\u0000value"}',
    ],
)
def test_malformed_or_action_bearing_output_is_rejected_without_echo(raw: bytes) -> None:
    with pytest.raises(
        ValueError,
        match=VALIDATION_ERRORS,
    ) as failure:
        decode_result(ClarifyGoal(SOURCE, "Synthetic"), raw)
    assert "private" not in str(failure.value)


def test_semantic_catalogue_membership_and_distinctness() -> None:
    candidate = Candidate(uuid4(), "Synthetic")
    task = SuggestSubject(SOURCE, "Custom", (candidate,))
    assert decode_result(
        task, ('{"ids":["' + str(candidate.id) + '"]}').encode()
    ) == SubjectSuggestions((candidate.id,))
    with pytest.raises(
        ValueError,
        match=VALIDATION_ERRORS,
    ):
        decode_result(task, ('{"ids":["' + str(uuid4()) + '"]}').encode())
    for ids in ((candidate.id, candidate.id), tuple(uuid4() for _ in range(4))):
        with pytest.raises(
            ValueError,
            match=VALIDATION_ERRORS,
        ):
            SubjectSuggestions(ids)
    for candidates in (
        (),
        (candidate, candidate),
        tuple(Candidate(uuid4(), "Synthetic") for _ in range(21)),
    ):
        with pytest.raises(
            ValueError,
            match=VALIDATION_ERRORS,
        ):
            SuggestSubject(SOURCE, "Custom", candidates)


def test_result_success_once_and_cancellation_and_deadline_are_terminal() -> None:
    original = job()
    running = original.claim(uuid4(), 1, NOW)
    success = running.finish(ClarifiedGoal("Editable"), NOW)
    assert success.state == JobState.SUCCEEDED
    assert success.finish(ClarifiedGoal("Late"), NOW) is success
    assert success.cancel() is success
    assert running.cancel().finish(ClarifiedGoal("Late"), NOW).state == JobState.CANCELLED
    assert running.finish(ClarifiedGoal("Late"), original.deadline).state == JobState.EXPIRED
    assert original.claim(uuid4(), 1, original.deadline).state == JobState.EXPIRED
    assert original.state == JobState.QUEUED
    assert "Synthetic" not in repr(original)


@pytest.mark.parametrize("failure", list(Failure))
def test_retry_budget_and_deadline_are_bounded(failure: Failure) -> None:
    current = job().claim(uuid4(), 1, NOW)
    for number in range(1, 4):
        failed = current.fail(failure, NOW, timedelta(seconds=2))
        if failed.state != JobState.QUEUED:
            break
        current = failed.claim(uuid4(), number + 1, NOW + timedelta(seconds=2))
    assert failed.state == JobState.FAILED
    assert failed.attempts <= (2 if failure == Failure.INVALID_OUTPUT else 3)
    assert current.fail(failure, current.deadline, timedelta(0)).state == JobState.EXPIRED
    assert failed.fail(failure, NOW, timedelta(0)) is failed


def test_invalid_job_versions_and_due_state() -> None:
    with pytest.raises(
        ValueError,
        match=VALIDATION_ERRORS,
    ):
        Versions("")
    with pytest.raises(
        ValueError,
        match=VALIDATION_ERRORS,
    ):
        Versions("x" * 101)
    original = job()
    invalid: tuple[Callable[[], AiJob], ...] = (
        lambda: replace(original, digest=b"short"),
        lambda: replace(original, attempts=4),
        lambda: replace(original, generation=-1),
        lambda: replace(original, deadline=NOW),
        lambda: replace(original, state=JobState.SUCCEEDED),
    )
    for operation in invalid:
        with pytest.raises(ValueError, match=r"digest|deadline|Attempt|successful"):
            operation()
    with pytest.raises(
        ValueError,
        match=VALIDATION_ERRORS,
    ):
        replace(original, not_before=NOW + timedelta(seconds=1)).claim(uuid4(), 1, NOW)
    with pytest.raises(
        ValueError,
        match=VALIDATION_ERRORS,
    ):
        original.cancel().claim(uuid4(), 1, NOW)
    for delay in (timedelta(seconds=-1), timedelta(minutes=6)):
        with pytest.raises(
            ValueError,
            match=VALIDATION_ERRORS,
        ):
            original.claim(uuid4(), 1, NOW).fail(Failure.TRANSIENT, NOW, delay)


@pytest.mark.parametrize(
    ("kind", "text", "candidates"),
    [
        (AiKind.TRIAGE_REPORT, None, ()),
        (AiKind.CLARIFY_GOAL, None, ()),
        (AiKind.CLARIFY_GOAL, " ", ()),
        (AiKind.CLARIFY_GOAL, "x" * 241, ()),
        (AiKind.ASSESS_PHOTO, "text", ()),
        (AiKind.SUGGEST_SUBJECT, None, ()),
        (AiKind.ASSESS_PHOTO, None, (UUID(int=2),)),
        (AiKind.SUGGEST_SUBJECT, None, (UUID(int=2), UUID(int=2))),
    ],
)
def test_student_submission_has_no_internal_or_unbounded_input(
    kind: AiKind, text: str | None, candidates: tuple[UUID, ...]
) -> None:
    with pytest.raises(
        ValueError,
        match=VALIDATION_ERRORS,
    ):
        StudentSubmission(kind, SOURCE, text, candidates)


@pytest.mark.parametrize(
    "operation",
    [
        lambda p: replace(p, queue_limit=101),
        lambda p: replace(p, queue_limit=0),
        lambda p: replace(p, internal_reserve=100),
        lambda p: replace(p, student_outstanding=3),
        lambda p: replace(p, bucket_capacity=6),
        lambda p: replace(p, refill_seconds=0),
        lambda p: replace(p, interactive_lifetime=timedelta(0)),
        lambda p: replace(p, internal_lifetime=timedelta(hours=1)),
    ],
)
def test_admission_configuration_cannot_exceed_database_limits(
    operation: "Callable[[AdmissionPolicy], AdmissionPolicy]",
) -> None:
    with pytest.raises(ValueError, match="safety"):
        operation(AdmissionPolicy())
