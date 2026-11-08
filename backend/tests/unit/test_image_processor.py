import asyncio
import struct
import threading
import zlib
from io import BytesIO

import pytest
from PIL import Image, PngImagePlugin

from studymate.application.media.processing import (
    MAX_DISPLAY_EDGE,
    MAX_SOURCE_BYTES,
    MAX_SOURCE_EDGE,
    ImageFailure,
    ImageProcessorUnavailableError,
    InvalidImageError,
    ProcessedImage,
)
from studymate.infrastructure.media import images
from studymate.infrastructure.media.images import BoundedImageProcessor
from tests.image_fixture import encoded


@pytest.mark.parametrize("format_name", ["PNG", "JPEG"])
async def test_photo_output_is_pixel_only_bounded_jpeg(format_name: str) -> None:
    processor = BoundedImageProcessor()
    try:
        result = await processor.process(
            encoded(format_name=format_name, size=(MAX_DISPLAY_EDGE + 100, 100))
        )
    finally:
        await processor.close()
    assert result.content_type == "image/jpeg"
    assert result.width == MAX_DISPLAY_EDGE
    assert result.height < result.width
    with Image.open(BytesIO(result.data)) as output:
        assert output.format == "JPEG"
        assert output.size == (result.width, result.height)
        assert output.mode == "RGB"
        assert not output.getexif()
        assert "icc_profile" not in output.info
        assert "exif" not in output.info
    assert "data=" not in repr(result)


async def test_photo_metadata_and_orientation_do_not_leak_to_output() -> None:
    data = BytesIO()
    with Image.new("RGB", (20, 10), "red") as original:
        exif = Image.Exif()
        exif[274] = 6
        exif[315] = "Private student author"
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("private", "Private location")
        original.save(data, format="PNG", exif=exif, pnginfo=metadata)
    processor = BoundedImageProcessor()
    try:
        result = await processor.process(data.getvalue())
    finally:
        await processor.close()
    assert (result.width, result.height) == (10, 20)
    assert b"Private" not in result.data
    with Image.open(BytesIO(result.data)) as output:
        assert not output.getexif()
        assert "private" not in output.info


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (b"GIF89a", ImageFailure.UNSUPPORTED_FORMAT),
        (b"\xff\xd8\xffbroken", ImageFailure.INVALID_IMAGE),
        (b"x" * (MAX_SOURCE_BYTES + 1), ImageFailure.TOO_LARGE),
    ],
)
async def test_invalid_photo_has_safe_specific_failure(data: bytes, reason: ImageFailure) -> None:
    processor = BoundedImageProcessor()
    try:
        with pytest.raises(InvalidImageError) as failed:
            await processor.process(data)
        assert failed.value.reason == reason
        assert str(failed.value) == reason.value
    finally:
        await processor.close()


async def test_decoded_pixel_and_edge_limits_apply_before_loading() -> None:
    small = encoded()
    dimensions = struct.pack(">II", 6000, 5000)
    header = small[12:16] + dimensions + small[24:29]
    pixel_bomb = (
        small[:16] + dimensions + small[24:29] + struct.pack(">I", zlib.crc32(header)) + small[33:]
    )
    processor = BoundedImageProcessor()
    try:
        for data in (pixel_bomb, encoded(size=(MAX_SOURCE_EDGE + 1, 1))):
            with pytest.raises(InvalidImageError) as failed:
                await processor.process(data)
            assert failed.value.reason == ImageFailure.DIMENSIONS_EXCEEDED
    finally:
        await processor.close()


async def test_animation_is_rejected_instead_of_silently_selecting_frame() -> None:
    data = BytesIO()
    with Image.new("RGB", (10, 10), "red") as first, Image.new("RGB", (10, 10), "blue") as second:
        first.save(data, format="PNG", save_all=True, append_images=[second], duration=100)
    processor = BoundedImageProcessor()
    try:
        with pytest.raises(InvalidImageError) as failed:
            await processor.process(data.getvalue())
        assert failed.value.reason == ImageFailure.ANIMATED_IMAGE
    finally:
        await processor.close()


async def test_cancelled_caller_does_not_release_still_running_codec_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = threading.Event()
    request_thread = threading.get_ident()

    def controlled(data: bytes) -> ProcessedImage:
        assert data == b"private bytes"
        assert threading.get_ident() != request_thread
        loop.call_soon_threadsafe(started.set)
        assert release.wait(timeout=5)
        return ProcessedImage(b"safe output", 1, 1)

    monkeypatch.setattr(images, "_convert", controlled)
    processor = BoundedImageProcessor()
    task = asyncio.create_task(processor.process(b"private bytes"))
    try:
        await asyncio.wait_for(started.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(ImageProcessorUnavailableError):
            await processor.process(b"second allocation")
    finally:
        release.set()
        await processor.close()
    with pytest.raises(ImageProcessorUnavailableError):
        await processor.process(b"after shutdown")
