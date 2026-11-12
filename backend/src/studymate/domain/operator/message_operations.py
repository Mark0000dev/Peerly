"""Actual terminal message operations; cancelled sends have no retained message content."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from studymate.domain.messaging import MessageOutcome
from studymate.domain.time import require_aware

OPERATOR_MESSAGE_OPERATIONS_PAGE_SIZE = 50


@dataclass(frozen=True, slots=True)
class OperatorOperationMessage:
    id: UUID
    sequence: int
    sent_at: datetime
    text: str | None = field(repr=False)
    image_id: UUID | None
    image_version: int | None
    image_attempt_id: UUID | None


@dataclass(frozen=True, slots=True)
class OperatorMessageOperation:
    id: UUID
    conversation_id: UUID
    low_id: UUID
    high_id: UUID
    author_id: UUID
    client_message_id: UUID
    state: MessageOutcome
    message_id: UUID | None
    cancelled_at: datetime | None
    terminal_at: datetime
    message: OperatorOperationMessage | None = field(repr=False)

    def __post_init__(self) -> None:
        require_aware(self.terminal_at)
        if self.state == MessageOutcome.CONFIRMED:
            if (
                self.message is None
                or self.message_id != self.message.id
                or self.cancelled_at is not None
                or self.terminal_at != self.message.sent_at
            ):
                raise ValueError("Confirmed operation requires its actual message source")
        elif (
            self.message is not None
            or self.message_id is not None
            or self.cancelled_at != self.terminal_at
        ):
            raise ValueError("Cancelled operation has only its actual cancellation time")
