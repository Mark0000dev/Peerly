from dataclasses import replace
from datetime import timedelta
from uuid import UUID

import pytest

from studymate.domain.messaging import (
    MAX_MESSAGE_LENGTH,
    ChatConversation,
    ConfirmedMessage,
    MessageContent,
    MessageOperation,
    MessageOutcome,
)
from studymate.domain.relationships import AccountPair
from tests.unit.identity_store import NOW

PAIR = AccountPair.between(UUID(int=1), UUID(int=2))


def message() -> ConfirmedMessage:
    return ConfirmedMessage(
        UUID(int=3),
        UUID(int=4),
        UUID(int=5),
        PAIR,
        PAIR.low,
        UUID(int=6),
        1,
        MessageContent("Private synthetic text"),
        NOW,
    )


def test_confirmed_text_preserves_intentional_indentation_and_newlines() -> None:
    text = "  SELECT *\n\tFROM synthetic_table;  "
    value = replace(message(), content=MessageContent(text))
    assert value.content.text == text
    assert text not in repr(value)


@pytest.mark.parametrize(
    "text", ["", "  \n\t ", "bad\x00text", "bad\rtext", "bad\ud800", "x" * (MAX_MESSAGE_LENGTH + 1)]
)
def test_invalid_text_is_rejected_without_echoing_private_input(text: str) -> None:
    with pytest.raises(ValueError, match=r"Text|Message") as error:
        MessageContent(text)
    if text:
        assert text not in str(error.value)


def test_message_can_have_one_image_with_optional_real_caption() -> None:
    image_id = UUID(int=7)
    assert MessageContent(image_id=image_id).image_id == image_id
    assert MessageContent("A caption", image_id).text == "A caption"
    assert MessageContent("x" * MAX_MESSAGE_LENGTH).text is not None
    with pytest.raises(ValueError, match="text or one image"):
        MessageContent()


def test_sequence_is_authority_even_if_wall_time_moves_backwards() -> None:
    first = message()
    second = replace(
        first,
        id=UUID(int=9),
        client_message_id=UUID(int=10),
        sequence=2,
        sent_at=NOW - timedelta(seconds=1),
    )
    assert second.sequence > first.sequence
    assert second.sent_at < first.sent_at


@pytest.mark.parametrize("sequence", [True, 0, -1])
def test_confirmed_sequence_must_be_positive(sequence: int) -> None:
    with pytest.raises(ValueError, match="positive sequence"):
        replace(message(), sequence=sequence)


def test_message_author_and_timestamp_are_real_source_invariants() -> None:
    with pytest.raises(ValueError, match="participant"):
        replace(message(), author_id=UUID(int=100))
    with pytest.raises(ValueError, match="timezone"):
        replace(message(), sent_at=NOW.replace(tzinfo=None))


def test_operation_records_confirmed_or_cancelled_never_both() -> None:
    sent = message()
    confirmed = MessageOperation(
        sent.operation_id,
        sent.conversation_id,
        sent.pair,
        sent.author_id,
        sent.client_message_id,
        sent,
    )
    assert confirmed.outcome == MessageOutcome.CONFIRMED
    cancelled = replace(confirmed, message=None, cancelled_at=NOW)
    assert cancelled.outcome == MessageOutcome.CANCELLED
    with pytest.raises(ValueError, match="one terminal outcome"):
        replace(confirmed, cancelled_at=NOW)
    with pytest.raises(ValueError, match="one terminal outcome"):
        replace(cancelled, cancelled_at=None)
    with pytest.raises(ValueError, match="timezone"):
        replace(cancelled, cancelled_at=NOW.replace(tzinfo=None))


@pytest.mark.parametrize(
    "changed",
    [
        replace(message(), operation_id=UUID(int=100)),
        replace(message(), conversation_id=UUID(int=100)),
        replace(message(), pair=AccountPair.between(PAIR.low, UUID(int=20))),
        replace(message(), author_id=PAIR.high),
        replace(message(), client_message_id=UUID(int=100)),
    ],
)
def test_operation_cannot_claim_another_confirmed_message(changed: ConfirmedMessage) -> None:
    sent = message()
    with pytest.raises(ValueError, match="immutable operation"):
        MessageOperation(
            sent.operation_id,
            sent.conversation_id,
            sent.pair,
            sent.author_id,
            sent.client_message_id,
            changed,
        )


def test_conversation_needs_an_actual_accepted_revision_and_positive_head() -> None:
    value = ChatConversation(UUID(int=1), UUID(int=2), PAIR, UUID(int=3), 2, 1)
    assert value.next_message_sequence == 1
    for version in (True, 0, 1):
        with pytest.raises(ValueError, match="accepted request revision"):
            replace(value, accepted_request_version=version)
    for sequence in (True, 0, -1):
        with pytest.raises(ValueError, match="positive"):
            replace(value, next_message_sequence=sequence)
