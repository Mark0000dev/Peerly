import asyncio
from uuid import uuid4

import pytest

from studymate.application.ai.ports import AiExecutorError
from studymate.domain.ai.jobs import Failure
from studymate.domain.media import MAX_PHOTO_BYTES, MediaObjectKind, MediaObjectRef
from studymate.infrastructure.ai.photos import RetainedDisplayReader
from tests.integration.media_fixture import Storage


async def test_reader_fetches_only_the_owned_prepared_retained_display_reference() -> None:
    reference = MediaObjectRef(uuid4(), MediaObjectKind.DISPLAY, uuid4())
    storage = Storage(b"")
    storage.retained[reference] = b"\xff\xd8\xffsynthetic-display"
    assert (
        await RetainedDisplayReader(storage).display_image(reference) == storage.retained[reference]
    )
    for kind in (MediaObjectKind.UPLOAD, MediaObjectKind.ORIGINAL):
        invalid = MediaObjectRef(
            reference.upload_id,
            kind,
            None if kind == MediaObjectKind.UPLOAD else reference.attempt_id,
        )
        with pytest.raises(AiExecutorError) as denied:
            await RetainedDisplayReader(storage).display_image(invalid)
        assert denied.value.failure == Failure.INVALID_INPUT


@pytest.mark.parametrize(
    ("encoded", "failure"),
    [
        (b"", Failure.INVALID_INPUT),
        (b"not a jpeg", Failure.INVALID_INPUT),
        (b"\xff\xd8\xff" + b"x" * MAX_PHOTO_BYTES, Failure.INVALID_INPUT),
    ],
)
async def test_corrupt_or_oversized_display_is_not_sent_to_executor(
    encoded: bytes, failure: Failure
) -> None:
    reference = MediaObjectRef(uuid4(), MediaObjectKind.DISPLAY, uuid4())
    storage = Storage(b"")
    storage.retained[reference] = encoded
    with pytest.raises(AiExecutorError) as invalid:
        await RetainedDisplayReader(storage).display_image(reference)
    assert invalid.value.failure == failure


async def test_storage_missing_and_unavailability_have_safe_distinct_failures() -> None:
    reference = MediaObjectRef(uuid4(), MediaObjectKind.DISPLAY, uuid4())
    storage = Storage(b"")
    with pytest.raises(AiExecutorError) as missing:
        await RetainedDisplayReader(storage).display_image(reference)
    assert missing.value.failure == Failure.INVALID_INPUT
    storage.unavailable = True

    # Existing controlled storage only fails reads of uploads; use retained failure boundary below.
    class Unavailable(Storage):
        async def read(self, reference: MediaObjectRef) -> bytes:
            from studymate.application.media.storage import MediaStorageUnavailableError

            assert reference.kind == MediaObjectKind.DISPLAY
            raise MediaStorageUnavailableError("PRIVATE_STORAGE_DETAIL")

    with pytest.raises(AiExecutorError) as unavailable:
        await RetainedDisplayReader(Unavailable(b"")).display_image(reference)
    assert unavailable.value.failure == Failure.TRANSIENT
    assert "PRIVATE_STORAGE_DETAIL" not in str(unavailable.value)


async def test_cancelled_storage_read_does_not_invent_advice() -> None:
    started = asyncio.Event()

    class Paused(Storage):
        async def read(self, reference: MediaObjectRef) -> bytes:
            assert reference.kind == MediaObjectKind.DISPLAY
            started.set()
            await asyncio.Event().wait()
            raise AssertionError("Cancelled storage cannot return advice")

    reference = MediaObjectRef(uuid4(), MediaObjectKind.DISPLAY, uuid4())
    operation = asyncio.create_task(RetainedDisplayReader(Paused(b"")).display_image(reference))
    await started.wait()
    operation.cancel()
    with pytest.raises(asyncio.CancelledError):
        await operation
