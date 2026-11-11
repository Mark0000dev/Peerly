from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID

from studymate.application.operator.chat_image_ports import (
    OperatorChatImageFilters,
    OperatorChatImageHistoryHead,
    OperatorChatImageHistoryWindow,
    OperatorChatImageUploadRootPosition,
)
from studymate.domain.chat_images import ChatImageState
from studymate.domain.operator.chat_image_uploads import (
    OPERATOR_CHAT_IMAGE_PAGE_SIZE,
    OperatorChatImageAttempt,
    OperatorChatImageMatchingOperation,
    OperatorChatImageUploadRevision,
    OperatorChatImageUploadRoot,
)
from tests.unit.identity_store import NOW
from tests.unit.operator.store import TARGET, Store

FIRST_UPLOAD = UUID(int=801)
SECOND_UPLOAD = UUID(int=802)
DIGEST = bytes(range(32))


def revision(
    version: int, image_id: UUID = FIRST_UPLOAD, account_id: UUID = TARGET
) -> OperatorChatImageUploadRevision:
    return OperatorChatImageUploadRevision(
        image_id,
        account_id,
        UUID(int=900),
        UUID(int=image_id.int + 10000),
        version,
        ChatImageState.UPLOADING,
        NOW - timedelta(minutes=version),
        None,
        None,
        None,
    )


def root(image_id: UUID = FIRST_UPLOAD, account_id: UUID = TARGET) -> OperatorChatImageUploadRoot:
    return OperatorChatImageUploadRoot(
        image_id,
        account_id,
        UUID(int=900),
        account_id,
        UUID(int=1000),
        UUID(int=image_id.int + 10000),
        3,
        10,
        DIGEST,
        "image/png",
        NOW - timedelta(days=1),
        NOW + timedelta(minutes=5),
        NOW + timedelta(hours=1),
        revision(3, image_id, account_id),
    )


class ChatImageStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.accounts = {TARGET}
        self.roots = {FIRST_UPLOAD: root(), SECOND_UPLOAD: root(SECOND_UPLOAD)}
        self.revisions = {
            image_id: tuple(revision(version, image_id) for version in range(1, 4))
            for image_id in self.roots
        }
        self.attempt_rows: tuple[OperatorChatImageAttempt, ...] = ()
        self.operation: OperatorChatImageMatchingOperation | None = None
        self.account_override: UUID | None = None
        self.head_override: OperatorChatImageHistoryHead | None = None
        self.root_rows: tuple[OperatorChatImageUploadRoot, ...] | None = None
        self.revision_rows: tuple[OperatorChatImageUploadRevision, ...] | None = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["ChatImageStore"]:
        async with Store.transaction(self):
            yield self

    async def chat_image_account(self, account_id: UUID) -> UUID | None:
        self.queried()
        return (
            self.account_override
            if self.account_override is not None
            else account_id
            if account_id in self.accounts
            else None
        )

    async def chat_image_roots(
        self,
        account_id: UUID,
        filters: OperatorChatImageFilters,
        position: OperatorChatImageUploadRootPosition | None,
    ) -> tuple[OperatorChatImageUploadRoot, ...]:
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
                    <= (position.anchor_created_at, position.anchor_image_id.int)
                    and (row.created_at, row.id.int)
                    < (position.before_created_at, position.before_image_id.int)
                )
            )
        )
        return tuple(sorted(rows, key=lambda row: (row.created_at, row.id.int), reverse=True))[
            : OPERATOR_CHAT_IMAGE_PAGE_SIZE + 1
        ]

    async def chat_image_history_head(
        self, account_id: UUID, image_id: UUID
    ) -> OperatorChatImageHistoryHead | None:
        self.queried()
        if self.head_override is not None:
            return self.head_override
        value = self.roots.get(image_id)
        if value is None or value.account_id != account_id:
            return None
        return OperatorChatImageHistoryHead(
            value, max(row.version for row in self.revisions[image_id])
        )

    async def chat_image_history_revisions(
        self, account_id: UUID, image_id: UUID, window: OperatorChatImageHistoryWindow
    ) -> tuple[OperatorChatImageUploadRevision, ...]:
        self.queried()
        if self.revision_rows is not None:
            return self.revision_rows
        rows = (
            row
            for row in self.revisions[image_id]
            if row.account_id == account_id
            and row.version <= window.anchor_version
            and (window.before_version is None or row.version < window.before_version)
        )
        return tuple(sorted(rows, key=lambda row: row.version, reverse=True))[
            : OPERATOR_CHAT_IMAGE_PAGE_SIZE + 1
        ]

    async def chat_image_attempts_current(
        self, account_id: UUID, image_id: UUID
    ) -> tuple[OperatorChatImageAttempt, ...]:
        self.queried()
        assert account_id in self.accounts
        assert image_id in self.roots
        return self.attempt_rows

    async def chat_image_matching_operation(
        self, account_id: UUID, image_id: UUID
    ) -> OperatorChatImageMatchingOperation | None:
        self.queried()
        assert account_id in self.accounts
        assert image_id in self.roots
        return self.operation
