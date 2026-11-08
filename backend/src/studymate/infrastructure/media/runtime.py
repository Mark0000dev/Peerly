"""Explicit lifespan binding for storage used by immutable application services."""

from datetime import datetime

from studymate.application.media.storage import (
    MediaStorage,
    MediaStorageUnavailableError,
    UploadAccess,
)
from studymate.domain.media import MediaObjectRef


class MediaStorageHandle:
    def __init__(self) -> None:
        self._current: MediaStorage | None = None

    def bind(self, storage: MediaStorage) -> None:
        if self._current is not None:
            raise RuntimeError("Media storage is already bound")
        self._current = storage

    def unbind(self) -> None:
        self._current = None

    def _storage(self) -> MediaStorage:
        if self._current is None:
            raise MediaStorageUnavailableError
        return self._current

    async def upload_access(
        self, reference: MediaObjectRef, content_type: str, expires_at: datetime
    ) -> UploadAccess:
        return await self._storage().upload_access(reference, content_type, expires_at)

    async def read(self, reference: MediaObjectRef) -> bytes:
        return await self._storage().read(reference)

    async def retain(self, reference: MediaObjectRef, data: bytes, content_type: str) -> None:
        await self._storage().retain(reference, data, content_type)

    async def remove_transport(self, reference: MediaObjectRef) -> None:
        await self._storage().remove_transport(reference)
