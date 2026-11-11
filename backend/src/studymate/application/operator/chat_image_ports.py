"""Explicit retained chat image root/history ports under the actual operator audit transaction."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from studymate.application.operator.cursors import OperatorCursorScope
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.chat_images import ChatImageState
from studymate.domain.operator.chat_image_uploads import (
    MAX_OPERATOR_CHAT_IMAGE_VERSION,
    OperatorChatImageAttempt,
    OperatorChatImageMatchingOperation,
    OperatorChatImageUploadRevision,
    OperatorChatImageUploadRoot,
)
from studymate.domain.time import require_aware


@dataclass(frozen=True, slots=True)
class OperatorChatImageFilters:
    conversation_id: UUID | None = None
    state: ChatImageState | None = None
    created_from: datetime | None = None
    created_before: datetime | None = None

    def __post_init__(self) -> None:
        for value in (self.created_from, self.created_before):
            if value is not None:
                require_aware(value)
        if (
            self.created_from is not None
            and self.created_before is not None
            and self.created_from >= self.created_before
        ):
            raise ValueError("Chat image root search needs a nonempty half-open time interval")

    def fingerprint_parts(self) -> tuple[str, ...]:
        return (
            "operator.chat-image-roots.v1",
            str(self.conversation_id) if self.conversation_id is not None else "",
            self.state.value if self.state is not None else "",
            self.created_from.astimezone(UTC).isoformat() if self.created_from is not None else "",
            self.created_before.astimezone(UTC).isoformat()
            if self.created_before is not None
            else "",
        )

    def matches(self, upload: OperatorChatImageUploadRoot) -> bool:
        return not (
            (self.conversation_id is not None and upload.conversation_id != self.conversation_id)
            or (self.state is not None and upload.current_revision.state != self.state)
            or (self.created_from is not None and upload.created_at < self.created_from)
            or (self.created_before is not None and upload.created_at >= self.created_before)
        )


@dataclass(frozen=True, slots=True)
class OperatorChatImageUploadRootPosition:
    anchor_created_at: datetime
    anchor_image_id: UUID
    before_created_at: datetime
    before_image_id: UUID

    def __post_init__(self) -> None:
        require_aware(self.anchor_created_at)
        require_aware(self.before_created_at)
        if (self.before_created_at, self.before_image_id.int) > (
            self.anchor_created_at,
            self.anchor_image_id.int,
        ):
            raise ValueError("Chat image root position exceeds its actual metadata anchor")


@dataclass(frozen=True, slots=True)
class OperatorChatImageHistoryHead:
    upload: OperatorChatImageUploadRoot
    latest_version: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.latest_version, bool)
            or not 1 <= self.latest_version <= MAX_OPERATOR_CHAT_IMAGE_VERSION
        ):
            raise ValueError("Chat image history head requires an actual positive source version")


@dataclass(frozen=True, slots=True)
class OperatorChatImageHistoryPosition:
    anchor_version: int
    before_version: int

    def __post_init__(self) -> None:
        if (
            any(
                isinstance(value, bool) or not 1 <= value <= MAX_OPERATOR_CHAT_IMAGE_VERSION
                for value in (self.anchor_version, self.before_version)
            )
            or self.before_version > self.anchor_version
        ):
            raise ValueError("Chat image history position exceeds its actual version anchor")


@dataclass(frozen=True, slots=True)
class OperatorChatImageHistoryWindow:
    anchor_version: int
    before_version: int | None


class OperatorChatImageCursorCodec(Protocol):
    def encode_roots(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        fingerprint: bytes,
        position: OperatorChatImageUploadRootPosition,
    ) -> str: ...

    def decode_roots(
        self, scope: OperatorCursorScope, account_id: UUID, fingerprint: bytes, token: str
    ) -> OperatorChatImageUploadRootPosition: ...

    def encode_history(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        image_id: UUID,
        position: OperatorChatImageHistoryPosition,
    ) -> str: ...

    def decode_history(
        self, scope: OperatorCursorScope, account_id: UUID, image_id: UUID, token: str
    ) -> OperatorChatImageHistoryPosition: ...


class OperatorChatImageTransaction(OperatorAuditTransaction, Protocol):
    async def chat_image_account(self, account_id: UUID) -> UUID | None:
        """Actual AccountRecord existence without student/target lifecycle filtering."""
        ...

    async def chat_image_roots(
        self,
        account_id: UUID,
        filters: OperatorChatImageFilters,
        position: OperatorChatImageUploadRootPosition | None,
    ) -> tuple[OperatorChatImageUploadRoot, ...]:
        """At most51, created_at/idDESC; current metadata, NOT a replay/commit watermark."""
        ...

    async def chat_image_history_head(
        self, account_id: UUID, image_id: UUID
    ) -> OperatorChatImageHistoryHead | None:
        """Exact owned root plus max ALL stored revisions, not its current pointer."""
        ...

    async def chat_image_history_revisions(
        self, account_id: UUID, image_id: UUID, window: OperatorChatImageHistoryWindow
    ) -> tuple[OperatorChatImageUploadRevision, ...]:
        """At most51 exact raw owned revisions/versionDESC; no current catalogue reconstruction."""
        ...

    async def chat_image_attempts_current(
        self, account_id: UUID, image_id: UUID
    ) -> tuple[OperatorChatImageAttempt, ...]:
        """At most3 current recorded attempts; these outcomes are mutable."""
        ...

    async def chat_image_matching_operation(
        self, account_id: UUID, image_id: UUID
    ) -> OperatorChatImageMatchingOperation | None:
        """Only actual author/conversation/client-ID match, never an attachment association."""
        ...


class OperatorChatImageUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[OperatorChatImageTransaction]: ...
