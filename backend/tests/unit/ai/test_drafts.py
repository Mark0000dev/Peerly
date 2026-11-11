from dataclasses import replace
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from studymate.application.ai.drafts import draft_snapshot_source
from studymate.application.ai.ports import DraftSourceIntent, StudentSubmission
from studymate.domain.ai.tasks import (
    AiKind,
    ClarifiedGoal,
    ClarifyGoal,
    DraftSnapshotSource,
    GoalTextTarget,
    Priority,
    ReportTriage,
    Source,
    SuggestSubject,
    TriageReport,
    validate_result,
)
from studymate.infrastructure.ai.codec import TASK_CODEC, decode_result, output_model

if TYPE_CHECKING:
    from collections.abc import Callable


def draft() -> StudentSubmission:
    return StudentSubmission(
        AiKind.CLARIFY_GOAL, DraftSourceIntent(uuid4(), 1), "  Synthetic résumé context  "
    )


def test_hash_uses_server_actual_validated_content_not_client_identity_or_claimed_hash() -> None:
    submitted = draft()
    source = draft_snapshot_source(submitted)
    assert source.id == submitted.source.id
    assert source.version == submitted.source.version
    assert len(source.content_hash) == len("a" * 64)
    assert (
        draft_snapshot_source(replace(submitted, text="Changed")).content_hash
        != source.content_hash
    )
    assert (
        draft_snapshot_source(replace(submitted, target=GoalTextTarget.TOPIC)).content_hash
        != source.content_hash
    )
    assert (
        draft_snapshot_source(replace(submitted, source=DraftSourceIntent(uuid4(), 2))).content_hash
        == source.content_hash
    )
    task = ClarifyGoal(source, submitted.text or "")
    assert task.text == "  Synthetic résumé context  "
    assert TASK_CODEC.validate_json(TASK_CODEC.dump_json(task)) == task
    with pytest.raises(ValueError, match="explicit"):
        draft_snapshot_source(replace(submitted, source=Source(uuid4(), 1)))


def test_catalogue_subset_hash_is_canonical_but_changed_label_or_id_is_distinct() -> None:
    first, second = uuid4(), uuid4()
    submitted = StudentSubmission(
        AiKind.SUGGEST_SUBJECT,
        DraftSourceIntent(uuid4(), 1),
        candidate_ids=(first, second),
        label="Synthetic custom",
    )
    source = draft_snapshot_source(submitted)
    assert draft_snapshot_source(replace(submitted, candidate_ids=(second, first))) == source
    assert (
        draft_snapshot_source(replace(submitted, label="Changed")).content_hash
        != source.content_hash
    )
    assert (
        draft_snapshot_source(replace(submitted, candidate_ids=(uuid4(),))).content_hash
        != source.content_hash
    )


@pytest.mark.parametrize(
    ("target", "limit"), [(GoalTextTarget.TOPIC, 80), (GoalTextTarget.CONTEXT, 240)]
)
def test_explicit_target_limits_apply_to_input_schema_and_semantic_result(
    target: GoalTextTarget, limit: int
) -> None:
    submitted = replace(draft(), text="x" * limit, target=target)
    task = ClarifyGoal(draft_snapshot_source(submitted), submitted.text or "", target)
    assert output_model(task).model_json_schema()["properties"]["suggestion"]["maxLength"] == limit
    assert decode_result(task, ('{"suggestion":"' + "x" * limit + '"}').encode()) == ClarifiedGoal(
        "x" * limit
    )
    with pytest.raises(ValueError, match="bounded"):
        replace(submitted, text="x" * (limit + 1))
    if target == GoalTextTarget.TOPIC:
        with pytest.raises(ValueError, match="conform"):
            validate_result(task, ClarifiedGoal("x" * (limit + 1)))


def test_legacy_private_resource_snapshots_decode_without_weakening_new_draft_tags() -> None:
    identifier = UUID(int=1)
    raw = (
        '{"source":{"id":"' + str(identifier) + '","version":1},"text":"Legacy explicit text"}'
    ).encode()
    decoded = TASK_CODEC.validate_json(raw)
    assert isinstance(decoded, ClarifyGoal)
    assert decoded.source == Source(identifier, 1)
    assert decoded.target == GoalTextTarget.CONTEXT
    subject = (
        '{"source":{"id":"'
        + str(identifier)
        + '","version":1},"label":"Legacy custom","candidates":[{"id":"'
        + str(UUID(int=2))
        + '","label":"Synthetic candidate"}]}'
    ).encode()
    assert isinstance(TASK_CODEC.validate_json(subject), SuggestSubject)
    malformed = (
        '{"source":{"kind":"draft","id":"' + str(identifier) + '","version":1},"text":"Synthetic"}'
    ).encode()
    with pytest.raises(ValidationError, match="validation"):
        TASK_CODEC.validate_json(malformed)


@pytest.mark.parametrize("hash_value", ["", "z" * 64, "a" * 63, "a" * 65])
def test_draft_snapshot_must_have_real_bounded_server_hash(hash_value: str) -> None:
    with pytest.raises(ValueError, match="hash"):
        DraftSnapshotSource(uuid4(), 1, hash_value)


@pytest.mark.parametrize(
    "operation",
    [
        lambda: StudentSubmission(AiKind.ASSESS_PHOTO, DraftSourceIntent(uuid4(), 1)),
        lambda: StudentSubmission(
            AiKind.SUGGEST_SUBJECT, DraftSourceIntent(uuid4(), 1), candidate_ids=(uuid4(),)
        ),
        lambda: StudentSubmission(
            AiKind.SUGGEST_SUBJECT,
            DraftSourceIntent(uuid4(), 1),
            candidate_ids=(uuid4(),),
            label="x" * 81,
        ),
        lambda: StudentSubmission(
            AiKind.CLARIFY_GOAL, DraftSourceIntent(uuid4(), 1), "Synthetic", label="Unexpected"
        ),
        lambda: StudentSubmission(
            AiKind.SUGGEST_SUBJECT,
            Source(uuid4(), 1),
            candidate_ids=(uuid4(),),
            label="Client override",
        ),
        lambda: StudentSubmission(
            AiKind.ASSESS_PHOTO, Source(uuid4(), 1), target=GoalTextTarget.TOPIC
        ),
    ],
)
def test_unsaved_source_is_no_photo_or_other_resource_capability(
    operation: "Callable[[], StudentSubmission]",
) -> None:
    with pytest.raises(ValueError, match=r"requires|required|accept"):
        operation()


@pytest.mark.parametrize(
    "operation",
    [
        lambda: ClarifiedGoal(" " * 240 + "x"),
        lambda: TriageReport(Source(uuid4(), 1), " " * 4000 + "x"),
        lambda: ReportTriage(Priority.NORMAL, " " * 240 + "x"),
    ],
)
def test_whitespace_cannot_expand_retained_business_payload_past_raw_bounds(
    operation: "Callable[[], object]",
) -> None:
    with pytest.raises(ValueError, match="bound"):
        operation()
