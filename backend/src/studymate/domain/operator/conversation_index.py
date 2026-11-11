"""Finite retained conversation metadata, not message counts or timeline facts."""

from dataclasses import dataclass
from uuid import UUID

OPERATOR_CONVERSATION_PAGE_SIZE = 50


@dataclass(frozen=True, slots=True)
class OperatorConversationSummary:
    id: UUID
    relationship_id: UUID
    low_id: UUID
    high_id: UUID
    request_id: UUID
    accepted_request_version: int

    def __post_init__(self) -> None:
        if self.low_id.int >= self.high_id.int:
            raise ValueError("Conversation index requires its actual canonical participant pair")
        if isinstance(self.accepted_request_version, bool) or self.accepted_request_version <= 1:
            raise ValueError("Conversation index requires its actual accepted request revision")

    def includes(self, account_id: UUID) -> bool:
        return account_id in (self.low_id, self.high_id)
