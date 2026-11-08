from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from studymate.domain.relationships import AccountPair
from studymate.domain.time import require_aware


class StudyAnswer(StrEnum):
    YES = "yes"
    NOT_YET = "not_yet"
    DID_NOT_WORK_OUT = "did_not_work_out"


@dataclass(frozen=True, slots=True)
class StudyOutcomeRevision:
    id: UUID
    conversation_id: UUID
    pair: AccountPair
    actor_id: UUID
    version: int
    answer: StudyAnswer
    changed_at: datetime

    def __post_init__(self) -> None:
        self.pair.counterpart(self.actor_id)
        require_aware(self.changed_at)
        if isinstance(self.version, bool) or self.version < 1:
            raise ValueError("Study answer revision must be positive")


@dataclass(frozen=True, slots=True)
class StudyPromptReceipt:
    id: UUID
    conversation_id: UUID
    actor_id: UUID
    offered_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.offered_at)
