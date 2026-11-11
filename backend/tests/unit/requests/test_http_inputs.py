from uuid import uuid4

import pytest
from pydantic import ValidationError

from studymate.presentation.requests.inputs import (
    PreviewRequestBody,
    RequestActionBody,
    SendRequestBody,
    ViewRequestBody,
)


@pytest.mark.parametrize("text", [" ", "\x00secret", "x" * 241])
def test_send_rejects_invalid_reviewed_text(text: str) -> None:
    with pytest.raises(ValidationError):
        SendRequestBody(person_id=uuid4(), preview_id=uuid4(), text=text)


def test_send_preserves_exact_separate_unicode_fields_without_repr_leak() -> None:
    value = SendRequestBody(
        person_id=uuid4(), preview_id=uuid4(), text=" 😀 ", note="separate private note"
    )
    assert value.message().text == " 😀 "
    assert value.message().note == "separate private note"
    assert "private note" not in repr(value)
    assert "😀" not in repr(value)


@pytest.mark.parametrize("version", [True, 0, "1"])
def test_actions_require_actual_positive_integer_revision(version: object) -> None:
    with pytest.raises(ValidationError):
        RequestActionBody.model_validate({"person_id": str(uuid4()), "expected_version": version})


def test_write_inputs_forbid_actor_and_arbitrary_source_authority() -> None:
    with pytest.raises(ValidationError):
        PreviewRequestBody.model_validate(
            {"person_id": str(uuid4()), "mode": "find_help", "actor_id": str(uuid4())}
        )
    with pytest.raises(ValidationError):
        SendRequestBody.model_validate(
            {
                "person_id": str(uuid4()),
                "preview_id": str(uuid4()),
                "text": "reviewed",
                "context": {},
            }
        )
    with pytest.raises(ValidationError):
        ViewRequestBody.model_validate({"disclosure_id": str(uuid4()), "viewed_at": "clientclock"})
