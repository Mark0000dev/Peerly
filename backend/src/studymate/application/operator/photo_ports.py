"""Explicit retained photo root/history ports under the actual operator audit transaction."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from studymate.application.operator.cursors import OperatorCursorScope
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.media import PhotoUploadState
from studymate.domain.operator.photo_uploads import (
    MAX_OPERATOR_PHOTO_VERSION,
    OperatorMediaOrigin,
    OperatorPhotoAttempt,
    OperatorPhotoUploadRevision,
    OperatorPhotoUploadRoot,
    OperatorPublishedPhotoRef,
)
from studymate.domain.time import require_aware


@dataclass(frozen=True, slots=True)
class OperatorPhotoFilters:
    state: PhotoUploadState | None = None
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
            raise ValueError("Photo root search needs a nonempty half-open time interval")

    def fingerprint_parts(self) -> tuple[str, ...]:
        return (
            "operator.photo-roots.v1",
            self.state.value if self.state is not None else "",
            self.created_from.astimezone(UTC).isoformat() if self.created_from is not None else "",
            self.created_before.astimezone(UTC).isoformat()
            if self.created_before is not None
            else "",
        )

    def matches(self, upload: OperatorPhotoUploadRoot) -> bool:
        return not (
            (self.state is not None and upload.current_revision.state != self.state)
            or (self.created_from is not None and upload.created_at < self.created_from)
            or (self.created_before is not None and upload.created_at >= self.created_before)
        )


@dataclass(frozen=True, slots=True)
class OperatorPhotoUploadRootPosition:
    anchor_created_at: datetime
    anchor_upload_id: UUID
    before_created_at: datetime
    before_upload_id: UUID

    def __post_init__(self) -> None:
        require_aware(self.anchor_created_at)
        require_aware(self.before_created_at)
        if (self.before_created_at, self.before_upload_id.int) > (
            self.anchor_created_at,
            self.anchor_upload_id.int,
        ):
            raise ValueError("Photo root position exceeds its actual metadata anchor")


@dataclass(frozen=True, slots=True)
class OperatorPhotoHistoryHead:
    upload: OperatorPhotoUploadRoot
    latest_version: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.latest_version, bool)
            or not 1 <= self.latest_version <= MAX_OPERATOR_PHOTO_VERSION
        ):
            raise ValueError("Photo history head requires an actual positive source version")


@dataclass(frozen=True, slots=True)
class OperatorPhotoHistoryPosition:
    anchor_version: int
    before_version: int

    def __post_init__(self) -> None:
        if (
            any(
                isinstance(value, bool) or not 1 <= value <= MAX_OPERATOR_PHOTO_VERSION
                for value in (self.anchor_version, self.before_version)
            )
            or self.before_version > self.anchor_version
        ):
            raise ValueError("Photo history position exceeds its actual version anchor")


@dataclass(frozen=True, slots=True)
class OperatorPhotoHistoryWindow:
    anchor_version: int
    before_version: int | None


class OperatorPhotoCursorCodec(Protocol):
    def encode_roots(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        fingerprint: bytes,
        position: OperatorPhotoUploadRootPosition,
    ) -> str: ...

    def decode_roots(
        self, scope: OperatorCursorScope, account_id: UUID, fingerprint: bytes, token: str
    ) -> OperatorPhotoUploadRootPosition: ...

    def encode_history(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        upload_id: UUID,
        position: OperatorPhotoHistoryPosition,
    ) -> str: ...

    def decode_history(
        self, scope: OperatorCursorScope, account_id: UUID, upload_id: UUID, token: str
    ) -> OperatorPhotoHistoryPosition: ...


class OperatorPhotoTransaction(OperatorAuditTransaction, Protocol):
    async def photo_account(self, account_id: UUID) -> UUID | None:
        """Actual AccountRecord existence without student/target lifecycle filtering."""
        ...

    async def photo_roots(
        self,
        account_id: UUID,
        filters: OperatorPhotoFilters,
        position: OperatorPhotoUploadRootPosition | None,
    ) -> tuple[OperatorPhotoUploadRoot, ...]:
        """At most51, created_at/idDESC; current metadata, NOT a replay/commit watermark."""
        ...

    async def photo_history_head(
        self, account_id: UUID, upload_id: UUID
    ) -> OperatorPhotoHistoryHead | None:
        """Exact owned root plus max ALL stored revisions, not its current pointer."""
        ...

    async def photo_history_revisions(
        self, account_id: UUID, upload_id: UUID, window: OperatorPhotoHistoryWindow
    ) -> tuple[OperatorPhotoUploadRevision, ...]:
        """At most51 exact raw owned revisions/versionDESC; no current catalogue reconstruction."""
        ...

    async def photo_attempts_current(
        self, account_id: UUID, upload_id: UUID
    ) -> tuple[OperatorPhotoAttempt, ...]:
        """At most3 current recorded attempts; these outcomes are mutable."""
        ...

    async def photo_origins(
        self, account_id: UUID, upload_id: UUID
    ) -> tuple[OperatorMediaOrigin, ...]:
        """At most2 genuine retained created/queued origins; no ambient fallback."""
        ...

    async def latest_photo_publication(
        self, account_id: UUID, upload_id: UUID
    ) -> OperatorPublishedPhotoRef | None:
        """Latest recorded owned reference only, no object/access guarantee."""
        ...


class OperatorPhotoUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[OperatorPhotoTransaction]: ...
