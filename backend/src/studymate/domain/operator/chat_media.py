"""Exact retained chat image object identities; no transport references or implicit grants."""

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from studymate.domain.media import MediaObjectKind, MediaObjectRef


class OperatorChatMediaKind(StrEnum):
    ORIGINAL = "original"
    DISPLAY = "display"


@dataclass(frozen=True, slots=True)
class OperatorChatMediaRequest:
    account_id: UUID
    image_id: UUID
    attempt_id: UUID
    kind: OperatorChatMediaKind

    @property
    def reference(self) -> MediaObjectRef:
        return MediaObjectRef(self.image_id, MediaObjectKind(self.kind.value), self.attempt_id)


@dataclass(frozen=True, slots=True)
class OperatorChatMediaSource:
    """Proof returned ONLY after the actual image-owner + image-attempt source joins."""

    account_id: UUID
    image_id: UUID
    attempt_id: UUID

    def matches(self, request: OperatorChatMediaRequest) -> bool:
        return (self.account_id, self.image_id, self.attempt_id) == (
            request.account_id,
            request.image_id,
            request.attempt_id,
        )


@dataclass(frozen=True, slots=True)
class OperatorChatMediaBytes:
    kind: OperatorChatMediaKind
    data: bytes = field(repr=False)
