from datetime import UTC, datetime
from uuid import uuid4

import pytest

from studymate.application.media.storage import MediaStorageUnavailableError, UploadAccess
from studymate.domain.media import MediaObjectKind, MediaObjectRef
from studymate.infrastructure.media.runtime import MediaStorageHandle


class Storage:
    async def upload_access(
        self, reference: MediaObjectRef, content_type: str, expires_at: datetime
    ) -> UploadAccess:
        assert reference.kind == MediaObjectKind.UPLOAD
        assert content_type == "image/png"
        assert expires_at.tzinfo is not None
        return UploadAccess("https://synthetic.test", (("key", str(reference.upload_id)),))

    async def read(self, reference: MediaObjectRef) -> bytes:
        assert reference.kind == MediaObjectKind.UPLOAD
        return b"synthetic data"

    async def retain(self, reference: MediaObjectRef, data: bytes, content_type: str) -> None:
        assert reference.kind == MediaObjectKind.ORIGINAL
        assert data == b"synthetic data"
        assert content_type == "image/png"

    async def remove_transport(self, reference: MediaObjectRef) -> None:
        assert reference.kind == MediaObjectKind.UPLOAD


async def test_storage_handle_never_fakes_unconfigured_success_and_unbinds_on_shutdown() -> None:
    handle = MediaStorageHandle()
    reference = MediaObjectRef(uuid4(), MediaObjectKind.UPLOAD)
    with pytest.raises(MediaStorageUnavailableError):
        await handle.read(reference)
    handle.bind(Storage())
    with pytest.raises(RuntimeError, match="already bound"):
        handle.bind(Storage())
    assert (await handle.upload_access(reference, "image/png", datetime.now(UTC))).fields
    assert await handle.read(reference) == b"synthetic data"
    await handle.retain(
        MediaObjectRef(reference.upload_id, MediaObjectKind.ORIGINAL, uuid4()),
        b"synthetic data",
        "image/png",
    )
    await handle.remove_transport(reference)
    handle.unbind()
    with pytest.raises(MediaStorageUnavailableError):
        await handle.read(reference)
