from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID

from studymate.application.operator.photo_ports import (
    OperatorPhotoFilters,
    OperatorPhotoHistoryHead,
    OperatorPhotoHistoryWindow,
    OperatorPhotoUploadRootPosition,
)
from studymate.domain.media import PhotoUploadState
from studymate.domain.operator.photo_uploads import (
    OPERATOR_PHOTO_PAGE_SIZE,
    OperatorMediaOrigin,
    OperatorPhotoAttempt,
    OperatorPhotoUploadRevision,
    OperatorPhotoUploadRoot,
    OperatorPublishedPhotoRef,
)
from tests.unit.identity_store import NOW
from tests.unit.operator.store import TARGET, Store

FIRST_UPLOAD = UUID(int=801)
SECOND_UPLOAD = UUID(int=802)
DIGEST = bytes(range(32))


def revision(
    version: int, upload_id: UUID = FIRST_UPLOAD, account_id: UUID = TARGET
) -> OperatorPhotoUploadRevision:
    return OperatorPhotoUploadRevision(
        upload_id,
        account_id,
        version,
        PhotoUploadState.UPLOADING,
        NOW - timedelta(minutes=version),
        None,
        None,
    )


def root(upload_id: UUID = FIRST_UPLOAD, account_id: UUID = TARGET) -> OperatorPhotoUploadRoot:
    return OperatorPhotoUploadRoot(
        upload_id,
        account_id,
        3,
        0,
        10,
        DIGEST,
        "image/png",
        NOW - timedelta(days=1),
        NOW + timedelta(minutes=5),
        NOW + timedelta(hours=1),
        revision(3, upload_id, account_id),
    )


class PhotoStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.accounts = {TARGET}
        self.roots = {FIRST_UPLOAD: root(), SECOND_UPLOAD: root(SECOND_UPLOAD)}
        self.revisions = {
            upload_id: tuple(revision(version, upload_id) for version in range(1, 4))
            for upload_id in self.roots
        }
        self.attempt_rows: tuple[OperatorPhotoAttempt, ...] = ()
        self.origin_rows: tuple[OperatorMediaOrigin, ...] = ()
        self.publication: OperatorPublishedPhotoRef | None = None
        self.account_override: UUID | None = None
        self.head_override: OperatorPhotoHistoryHead | None = None
        self.root_rows: tuple[OperatorPhotoUploadRoot, ...] | None = None
        self.revision_rows: tuple[OperatorPhotoUploadRevision, ...] | None = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["PhotoStore"]:
        async with Store.transaction(self):
            yield self

    async def photo_account(self, account_id: UUID) -> UUID | None:
        self.queried()
        return (
            self.account_override
            if self.account_override is not None
            else account_id
            if account_id in self.accounts
            else None
        )

    async def photo_roots(
        self,
        account_id: UUID,
        filters: OperatorPhotoFilters,
        position: OperatorPhotoUploadRootPosition | None,
    ) -> tuple[OperatorPhotoUploadRoot, ...]:
        self.queried()
        if self.root_rows is not None:
            return self.root_rows
        rows = (
            row
            for row in self.roots.values()
            if row.account_id == account_id
            and filters.matches(row)
            and (
                position is None
                or (
                    (row.created_at, row.id.int)
                    <= (position.anchor_created_at, position.anchor_upload_id.int)
                    and (row.created_at, row.id.int)
                    < (position.before_created_at, position.before_upload_id.int)
                )
            )
        )
        return tuple(sorted(rows, key=lambda row: (row.created_at, row.id.int), reverse=True))[
            : OPERATOR_PHOTO_PAGE_SIZE + 1
        ]

    async def photo_history_head(
        self, account_id: UUID, upload_id: UUID
    ) -> OperatorPhotoHistoryHead | None:
        self.queried()
        if self.head_override is not None:
            return self.head_override
        value = self.roots.get(upload_id)
        if value is None or value.account_id != account_id:
            return None
        return OperatorPhotoHistoryHead(
            value, max(row.version for row in self.revisions[upload_id])
        )

    async def photo_history_revisions(
        self, account_id: UUID, upload_id: UUID, window: OperatorPhotoHistoryWindow
    ) -> tuple[OperatorPhotoUploadRevision, ...]:
        self.queried()
        if self.revision_rows is not None:
            return self.revision_rows
        rows = (
            row
            for row in self.revisions[upload_id]
            if row.account_id == account_id
            and row.version <= window.anchor_version
            and (window.before_version is None or row.version < window.before_version)
        )
        return tuple(sorted(rows, key=lambda row: row.version, reverse=True))[
            : OPERATOR_PHOTO_PAGE_SIZE + 1
        ]

    async def photo_attempts_current(
        self, account_id: UUID, upload_id: UUID
    ) -> tuple[OperatorPhotoAttempt, ...]:
        self.queried()
        assert account_id in self.accounts
        assert upload_id in self.roots
        return self.attempt_rows

    async def photo_origins(
        self, account_id: UUID, upload_id: UUID
    ) -> tuple[OperatorMediaOrigin, ...]:
        self.queried()
        assert account_id in self.accounts
        assert upload_id in self.roots
        return self.origin_rows

    async def latest_photo_publication(
        self, account_id: UUID, upload_id: UUID
    ) -> OperatorPublishedPhotoRef | None:
        self.queried()
        assert account_id in self.accounts
        assert upload_id in self.roots
        return self.publication
