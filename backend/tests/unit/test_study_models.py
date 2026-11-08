import pytest
from pydantic import ValidationError

from studymate.presentation.study_models import SaveGoalRequest, SaveHelpRequest


@pytest.mark.parametrize(
    "change",
    [
        {"subject": {"kind": "custom", "label": 42}},
        {"subject": {"kind": "custom", "label": ""}},
        {"topic": 42},
        {"context": "Private\x00context"},
        {"shared_learning": "true"},
    ],
)
def test_goal_inputs_do_not_coerce_private_text_or_opt_in(change: dict[str, object]) -> None:
    body = {"subject": {"kind": "custom", "label": "Synthetic"}, "expected_version": 0, **change}
    with pytest.raises(ValidationError):
        SaveGoalRequest.model_validate(body)


def test_help_notes_use_the_same_bounded_plain_text_rule() -> None:
    with pytest.raises(ValidationError):
        SaveHelpRequest.model_validate(
            {
                "subjects": [
                    {"subject_id": "00000000-0000-0000-0000-000000000001", "topic_note": 42}
                ],
                "expected_version": 0,
            }
        )
