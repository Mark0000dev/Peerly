from uuid import UUID

from pydantic import AwareDatetime, Field

from studymate.application.operator.message_operations import OperatorMessageOperationsPage
from studymate.domain.messaging import MessageOutcome
from studymate.domain.operator.message_operations import (
    OPERATOR_MESSAGE_OPERATIONS_PAGE_SIZE,
    OperatorMessageOperation,
)
from studymate.presentation.operator.models import ClosedModel


class OperatorMessageOperationsQuery(ClosedModel):
    cursor: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)


class OperatorOperationMessageResponse(ClosedModel):
    id: UUID
    sequence: int
    sent_at: AwareDatetime
    text: str | None = Field(repr=False)
    image_id: UUID | None
    image_version: int | None
    image_attempt_id: UUID | None


class OperatorMessageOperationResponse(ClosedModel):
    id: UUID
    conversation_id: UUID
    low_id: UUID
    high_id: UUID
    author_id: UUID
    client_message_id: UUID
    state: MessageOutcome
    message_id: UUID | None
    cancelled_at: AwareDatetime | None
    terminal_at: AwareDatetime
    message: OperatorOperationMessageResponse | None = Field(repr=False)


class OperatorMessageOperationsResponse(ClosedModel):
    account_id: UUID
    operations: tuple[OperatorMessageOperationResponse, ...] = Field(
        max_length=OPERATOR_MESSAGE_OPERATIONS_PAGE_SIZE, repr=False
    )
    next_cursor: str | None


def operation_response(value: OperatorMessageOperation) -> OperatorMessageOperationResponse:
    message = value.message
    return OperatorMessageOperationResponse(
        id=value.id,
        conversation_id=value.conversation_id,
        low_id=value.low_id,
        high_id=value.high_id,
        author_id=value.author_id,
        client_message_id=value.client_message_id,
        state=value.state,
        message_id=value.message_id,
        cancelled_at=value.cancelled_at,
        terminal_at=value.terminal_at,
        message=OperatorOperationMessageResponse(
            id=message.id,
            sequence=message.sequence,
            sent_at=message.sent_at,
            text=message.text,
            image_id=message.image_id,
            image_version=message.image_version,
            image_attempt_id=message.image_attempt_id,
        )
        if message is not None
        else None,
    )


def operations_response(value: OperatorMessageOperationsPage) -> OperatorMessageOperationsResponse:
    return OperatorMessageOperationsResponse(
        account_id=value.account_id,
        operations=tuple(operation_response(row) for row in value.operations),
        next_cursor=value.next_cursor,
    )
