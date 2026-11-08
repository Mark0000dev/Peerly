from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from studymate.application.operator.ports import OperatorAccountPosition, OperatorMessagePosition


class InvalidOperatorCursorError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class OperatorCursorScope:
    account_id: UUID
    access_version: int

    def __post_init__(self) -> None:
        if isinstance(self.access_version, bool) or self.access_version < 1:
            raise ValueError("Operator cursor needs an actual positive grant revision")


class OperatorCursorCodec(Protocol):
    def encode_accounts(
        self,
        scope: OperatorCursorScope,
        filters_fingerprint: bytes,
        position: OperatorAccountPosition,
    ) -> str: ...

    def decode_accounts(
        self, scope: OperatorCursorScope, filters_fingerprint: bytes, token: str, now: datetime
    ) -> OperatorAccountPosition: ...

    def encode_messages(
        self, scope: OperatorCursorScope, conversation_id: UUID, position: OperatorMessagePosition
    ) -> str: ...

    def decode_messages(
        self, scope: OperatorCursorScope, conversation_id: UUID, token: str
    ) -> OperatorMessagePosition: ...
