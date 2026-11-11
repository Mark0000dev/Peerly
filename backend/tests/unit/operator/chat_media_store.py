from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from uuid import UUID

from studymate.application.errors import StorageUnavailableError
from studymate.application.media.processing import ImageFailure, InvalidImageError
from studymate.application.media.storage import (
    MediaObjectMissingError,
    MediaStorageUnavailableError,
)
from studymate.application.operator.chat_media_ports import OperatorChatMediaAudit
from studymate.domain.media import MediaObjectRef
from studymate.domain.operator.chat_media import (
    OperatorChatMediaRequest,
    OperatorChatMediaSource,
)
from tests.unit.operator.store import TARGET, Store

IMAGE = UUID(int=901)
ATTEMPT = UUID(int=902)
PRIVATE_BYTES = b"private-retained-chat-image"


class ChatMediaStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.source: OperatorChatMediaSource | None = OperatorChatMediaSource(
            TARGET, IMAGE, ATTEMPT
        )
        self.media_audits: list[OperatorChatMediaAudit] = []
        self.transaction_count = 0
        self.in_transaction = False
        self.fail_commit = False

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["ChatMediaStore"]:
        assert not self.in_transaction
        self.transaction_count += 1
        before = self.media_audits.copy()
        self.in_transaction = True
        try:
            async with Store.transaction(self):
                yield self
                if self.fail_commit and self.media_audits:
                    raise StorageUnavailableError
        except BaseException:
            self.media_audits = before
            raise
        finally:
            self.in_transaction = False

    async def chat_media_source(
        self, request: OperatorChatMediaRequest
    ) -> OperatorChatMediaSource | None:
        assert self.in_transaction
        assert request.image_id is not None
        self.queried()
        return self.source

    async def save_chat_media_audit(self, inspection: OperatorChatMediaAudit) -> None:
        assert self.in_transaction
        self.media_audits.append(inspection)
        if self.fail_audit:
            raise StorageUnavailableError
        if self.expire_after_audit:
            self.clock = self.actor.session.expires_at


@dataclass(slots=True)
class ChatMediaReader:
    store: ChatMediaStore
    data: bytes = field(default=PRIVATE_BYTES, repr=False)
    missing: bool = False
    unavailable: bool = False
    timed_out: bool = False
    invalid_image: bool = False
    callback: Callable[[], Awaitable[None]] | None = None
    references: list[MediaObjectRef] = field(default_factory=list)

    async def read(self, reference: MediaObjectRef) -> bytes:
        assert not self.store.in_transaction
        self.references.append(reference)
        if self.callback is not None:
            await self.callback()
        if self.missing:
            raise MediaObjectMissingError
        if self.unavailable:
            raise MediaStorageUnavailableError
        if self.timed_out:
            raise TimeoutError
        if self.invalid_image:
            raise InvalidImageError(ImageFailure.TOO_LARGE)
        return self.data
