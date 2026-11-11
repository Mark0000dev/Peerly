from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from studymate.domain.media import MediaObjectRef


class MediaStorageUnavailableError(Exception):
    pass


class MediaUploadAccessExpiredError(Exception):
    pass


class MediaObjectMissingError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class UploadAccess:
    url: str = field(repr=False)
    fields: tuple[tuple[str, str], ...] = field(repr=False)


class MediaReader(Protocol):
    async def read(self, reference: MediaObjectRef) -> bytes: ...


class MediaStorage(MediaReader, Protocol):
    async def upload_access(
        self, reference: MediaObjectRef, content_type: str, expires_at: datetime
    ) -> UploadAccess: ...

    async def retain(self, reference: MediaObjectRef, data: bytes, content_type: str) -> None: ...

    async def remove_transport(self, reference: MediaObjectRef) -> None: ...
