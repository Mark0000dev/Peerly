from dataclasses import replace
from uuid import uuid4

import pytest
from pydantic import BaseModel, ValidationError

from studymate.application.messaging.history_ports import MessageHistoryPage
from studymate.application.messaging.participants import ChatParticipant, ChatParticipantState
from studymate.domain.messaging import ConfirmedMessage, MessageContent, MessageOperation
from studymate.domain.relationships import AccountPair
from studymate.presentation.messaging.models import (
    CancelledOperationResponse,
    ChatParticipantResponse,
    ConfirmedOperationResponse,
    MessageHistoryResponse,
    MessageResponse,
    SendMessageBody,
    UnobservedOperationResponse,
    history_response,
    message_response,
    participant_response,
    terminal_response,
)
from tests.unit.identity_store import NOW

RESPONSE_TYPES: tuple[type[BaseModel], ...] = (
    CancelledOperationResponse,
    ChatParticipantResponse,
    ConfirmedOperationResponse,
    MessageHistoryResponse,
    MessageResponse,
    UnobservedOperationResponse,
)


def message() -> ConfirmedMessage:
    pair = AccountPair.between(uuid4(), uuid4())
    return ConfirmedMessage(
        uuid4(),
        uuid4(),
        uuid4(),
        pair,
        pair.low,
        uuid4(),
        1,
        MessageContent("  Private multiline\n exact  "),
        NOW,
    )


@pytest.mark.parametrize("response_type", RESPONSE_TYPES)
def test_fixed_response_objects_are_closed_including_nested_definitions(
    response_type: type[BaseModel],
) -> None:
    schema = response_type.model_json_schema()
    assert schema["additionalProperties"] is False
    definitions = schema.get("$defs")
    if isinstance(definitions, dict):
        for definition in definitions.values():
            if isinstance(definition, dict) and definition.get("type") == "object":
                assert definition["additionalProperties"] is False


@pytest.mark.parametrize("text", ["", "  ", "bad\x00value", "x" * 2001])
def test_text_input_is_bounded_plain_text_and_never_image_authority(text: str) -> None:
    with pytest.raises(ValidationError):
        SendMessageBody(client_message_id=uuid4(), text=text)


def test_input_forbids_actor_and_context_injection() -> None:
    for field in ("actor_id", "system_prompt", "read_position"):
        with pytest.raises(ValidationError):
            SendMessageBody.model_validate(
                {"client_message_id": str(uuid4()), "text": "Explicit", field: str(uuid4())}
            )
    value = SendMessageBody(client_message_id=uuid4(), text="  Private multiline\n exact  ")
    assert value.content().text == value.text
    assert value.content().image_id is None
    assert "Private" not in repr(value)


def test_terminal_history_and_participant_mappings_retain_actual_fields_only() -> None:
    value = message()
    operation = MessageOperation(
        value.operation_id,
        value.conversation_id,
        value.pair,
        value.author_id,
        value.client_message_id,
        value,
    )
    confirmed = terminal_response(operation)
    assert isinstance(confirmed, ConfirmedOperationResponse)
    assert confirmed.message.sequence == value.sequence
    assert confirmed.message.text == value.content.text
    assert "Private" not in repr(confirmed)
    cancelled = terminal_response(replace(operation, message=None, cancelled_at=NOW))
    assert isinstance(cancelled, CancelledOperationResponse)
    assert cancelled.cancelled_at == NOW
    history = history_response(MessageHistoryPage((value,), None, value.sequence))
    assert history.messages == (message_response(value),)
    assert "unread" not in history.model_dump()
    assert "read_receipt" not in history.model_dump()
    masked = participant_response(ChatParticipant(value.pair.high, ChatParticipantState.DELETED))
    assert masked.display_name is None
    assert masked.photo_version is None


def test_confirmed_image_mapping_retains_actual_reference_and_nullable_caption() -> None:
    value = replace(message(), content=MessageContent(image_id=uuid4()))
    response = message_response(value)
    assert response.image_id == value.content.image_id
    assert response.text is None
    assert (
        SendMessageBody(client_message_id=uuid4(), image_id=response.image_id).content()
        == value.content
    )
