from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from studymate.application.messaging.history_ports import MessageHistoryPage
from studymate.application.messaging.participants import ChatParticipant, ChatParticipantState
from studymate.domain.messaging import (
    MAX_MESSAGE_LENGTH,
    ConfirmedMessage,
    MessageContent,
    MessageOperation,
)


class SendMessageBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    client_message_id: UUID
    text: str | None = Field(default=None, min_length=1, max_length=MAX_MESSAGE_LENGTH, repr=False)
    image_id: UUID | None = None

    def content(self) -> MessageContent:
        return MessageContent(self.text, self.image_id)

    @model_validator(mode="after")
    def valid_content(self) -> Self:
        self.content()
        return self


class MessageResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    message_id: UUID
    conversation_id: UUID
    author_id: UUID
    client_message_id: UUID
    sequence: int = Field(ge=1)
    text: str | None = Field(repr=False)
    image_id: UUID | None
    sent_at: datetime


class ConfirmedOperationResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    outcome: Literal["confirmed"] = "confirmed"
    operation_id: UUID
    conversation_id: UUID
    client_message_id: UUID
    message: MessageResponse = Field(repr=False)


class CancelledOperationResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    outcome: Literal["cancelled"] = "cancelled"
    operation_id: UUID
    conversation_id: UUID
    client_message_id: UUID
    cancelled_at: datetime


class UnobservedOperationResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    outcome: Literal["unobserved"] = "unobserved"
    conversation_id: UUID
    client_message_id: UUID


TerminalOperationResponse = Annotated[
    ConfirmedOperationResponse | CancelledOperationResponse, Field(discriminator="outcome")
]
OperationLookupResponse = Annotated[
    ConfirmedOperationResponse | CancelledOperationResponse | UnobservedOperationResponse,
    Field(discriminator="outcome"),
]


class MessageHistoryResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    messages: tuple[MessageResponse, ...] = Field(repr=False)
    next_cursor: str | None
    anchor_sequence: int = Field(ge=0)


class ChatParticipantResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    person_id: UUID
    state: ChatParticipantState
    display_name: str | None = Field(repr=False)
    photo_version: int | None


def message_response(value: ConfirmedMessage) -> MessageResponse:
    return MessageResponse(
        message_id=value.id,
        conversation_id=value.conversation_id,
        author_id=value.author_id,
        client_message_id=value.client_message_id,
        sequence=value.sequence,
        text=value.content.text,
        image_id=value.content.image_id,
        sent_at=value.sent_at,
    )


def terminal_response(
    value: MessageOperation,
) -> ConfirmedOperationResponse | CancelledOperationResponse:
    if value.message is not None:
        return ConfirmedOperationResponse(
            operation_id=value.id,
            conversation_id=value.conversation_id,
            client_message_id=value.client_message_id,
            message=message_response(value.message),
        )
    if value.cancelled_at is None:
        raise RuntimeError("Terminal operation lost its actual outcome")
    return CancelledOperationResponse(
        operation_id=value.id,
        conversation_id=value.conversation_id,
        client_message_id=value.client_message_id,
        cancelled_at=value.cancelled_at,
    )


def history_response(value: MessageHistoryPage) -> MessageHistoryResponse:
    return MessageHistoryResponse(
        messages=tuple(message_response(message) for message in value.messages),
        next_cursor=value.next_cursor,
        anchor_sequence=value.anchor_sequence,
    )


def participant_response(value: ChatParticipant) -> ChatParticipantResponse:
    return ChatParticipantResponse(
        person_id=value.account_id,
        state=value.state,
        display_name=value.name.value if value.name is not None else None,
        photo_version=value.photo_version,
    )
