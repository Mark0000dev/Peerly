"""Private bounded codec offload; the durable worker owns retries/admission."""

import asyncio
from concurrent.futures import Future, ThreadPoolExecutor
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from studymate.application.media.processing import (
    MAX_DISPLAY_EDGE,
    MAX_SOURCE_BYTES,
    MAX_SOURCE_EDGE,
    MAX_SOURCE_PIXELS,
    ImageFailure,
    ImageProcessorUnavailableError,
    InvalidImageError,
    ProcessedImage,
)
from studymate.domain.media import PhotoContentType

JPEG_SIGNATURE = b"\xff\xd8\xff"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_QUALITY = 88


def _convert(data: bytes) -> ProcessedImage:
    if len(data) > MAX_SOURCE_BYTES:
        raise InvalidImageError(ImageFailure.TOO_LARGE)
    if not data.startswith((JPEG_SIGNATURE, PNG_SIGNATURE)):
        raise InvalidImageError(ImageFailure.UNSUPPORTED_FORMAT)
    try:
        with Image.open(BytesIO(data), formats=("JPEG", "PNG")) as source:
            if (
                source.width * source.height > MAX_SOURCE_PIXELS
                or max(source.size) > MAX_SOURCE_EDGE
            ):
                raise InvalidImageError(ImageFailure.DIMENSIONS_EXCEEDED)
            if getattr(source, "n_frames", 1) != 1:
                raise InvalidImageError(ImageFailure.ANIMATED_IMAGE)
            source.load()
            oriented = ImageOps.exif_transpose(source)
            try:
                oriented.thumbnail((MAX_DISPLAY_EDGE, MAX_DISPLAY_EDGE), Image.Resampling.LANCZOS)
                rgba = oriented.convert("RGBA")
                try:
                    # A fresh pixel-only canvas cannot inherit EXIF/XMP/ICC or PNG text.
                    clean = Image.new("RGB", rgba.size, "white")
                    try:
                        clean.paste(rgba, mask=rgba.getchannel("A"))
                        output = BytesIO()
                        clean.save(
                            output, format="JPEG", quality=JPEG_QUALITY, exif=b"", icc_profile=None
                        )
                        return ProcessedImage(
                            output.getvalue(),
                            clean.width,
                            clean.height,
                            source_content_type=PhotoContentType.PNG
                            if source.format == "PNG"
                            else PhotoContentType.JPEG,
                        )
                    finally:
                        clean.close()
                finally:
                    rgba.close()
            finally:
                oriented.close()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise InvalidImageError(ImageFailure.DIMENSIONS_EXCEEDED) from error
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as error:
        raise InvalidImageError(ImageFailure.INVALID_IMAGE) from error


class BoundedImageProcessor:
    def __init__(self) -> None:
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="peerly-photo")
        self._slot = asyncio.Semaphore(1)
        self._closed = False

    @property
    def available(self) -> bool:
        return not self._closed and not self._slot.locked()

    async def process(self, data: bytes) -> ProcessedImage:
        if self._closed or self._slot.locked():
            raise ImageProcessorUnavailableError
        await self._slot.acquire()
        loop = asyncio.get_running_loop()
        try:
            future = self._pool.submit(_convert, data)
        except RuntimeError:
            self._slot.release()
            raise ImageProcessorUnavailableError from None

        def release(_completed: Future[ProcessedImage]) -> None:
            loop.call_soon_threadsafe(self._slot.release)

        future.add_done_callback(release)
        # Cancellation of the caller must not free the slot while native work continues.
        wrapped = asyncio.wrap_future(future)

        def consume_error(completed: asyncio.Future[ProcessedImage]) -> None:
            if not completed.cancelled():
                completed.exception()

        wrapped.add_done_callback(consume_error)
        return await asyncio.shield(wrapped)

    async def close(self) -> None:
        self._closed = True
        await asyncio.to_thread(self._pool.shutdown, wait=True, cancel_futures=True)
