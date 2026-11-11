"""Private monotonic read positions, never peer read receipts."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from studymate.domain.relationships import AccountPair
from studymate.domain.time import require_aware


@dataclass(frozen=True, slots=True)
class ConversationReadPosition:
    id: UUID
    conversation_id: UUID
    pair: AccountPair
    account_id: UUID
    version: int
    through_sequence: int
    acknowledged_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.acknowledged_at)
        if self.account_id not in (self.pair.low, self.pair.high):
            raise ValueError("Read position belongs to an accepted participant")
        for value in (self.version, self.through_sequence):
            if isinstance(value, bool) or value < 1:
                raise ValueError("Read position source and version must be positive")

    def advance(self, through_sequence: int, at: datetime) -> "ConversationReadPosition":
        require_aware(at)
        if isinstance(through_sequence, bool) or through_sequence < 1:
            raise ValueError("Read position source must be positive")
        if through_sequence <= self.through_sequence:
            return self
        return ConversationReadPosition(
            uuid4(),
            self.conversation_id,
            self.pair,
            self.account_id,
            self.version + 1,
            through_sequence,
            at,
        )
