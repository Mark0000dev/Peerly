"""Exact retained profile object identities; no transport references or implicit grants."""

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from studymate.domain.media import MediaObjectKind, MediaObjectRef


class OperatorProfileMediaKind(StrEnum):
    ORIGINAL = "original"
    DISPLAY = "display"


@dataclass(frozen=True, slots=True)
class OperatorProfileMediaRequest:
    account_id: UUID
    upload_id: UUID
    attempt_id: UUID
    kind: OperatorProfileMediaKind

    @property
    def reference(self) -> MediaObjectRef:
        return MediaObjectRef(self.upload_id, MediaObjectKind(self.kind.value), self.attempt_id)


@dataclass(frozen=True, slots=True)
class OperatorProfileMediaSource:
    """Proof returned ONLY after the actual upload-owner + upload-attempt source joins."""

    account_id: UUID
    upload_id: UUID
    attempt_id: UUID

    def matches(self, request: OperatorProfileMediaRequest) -> bool:
        return (self.account_id, self.upload_id, self.attempt_id) == (
            request.account_id,
            request.upload_id,
            request.attempt_id,
        )


@dataclass(frozen=True, slots=True)
class OperatorProfileMediaBytes:
    kind: OperatorProfileMediaKind
    data: bytes = field(repr=False)
