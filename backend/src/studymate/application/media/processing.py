from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from studymate.domain.media import MAX_PHOTO_BYTES, PhotoContentType

MAX_SOURCE_BYTES = MAX_PHOTO_BYTES
MAX_SOURCE_PIXELS = 24_000_000
MAX_SOURCE_EDGE = 8192
MAX_DISPLAY_EDGE = 1024


class ImageFailure(StrEnum):
    TOO_LARGE = "too_large"
    UNSUPPORTED_FORMAT = "unsupported_format"
    INVALID_IMAGE = "invalid_image"
    DIMENSIONS_EXCEEDED = "dimensions_exceeded"
    ANIMATED_IMAGE = "animated_image"


class InvalidImageError(Exception):
    def __init__(self, reason: ImageFailure) -> None:
        super().__init__(reason.value)
        self.reason = reason


class ImageProcessorUnavailableError(Exception):
    """Bounded processing slot is occupied or the processor has shut down."""


@dataclass(frozen=True, slots=True)
class ProcessedImage:
    data: bytes = field(repr=False)
    width: int
    height: int
    content_type: str = "image/jpeg"
    source_content_type: PhotoContentType = PhotoContentType.JPEG


class ImageProcessor(Protocol):
    @property
    def available(self) -> bool: ...

    async def process(self, data: bytes) -> ProcessedImage: ...
