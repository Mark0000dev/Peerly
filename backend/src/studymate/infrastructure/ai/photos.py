from dataclasses import dataclass

from studymate.application.ai.ports import AiExecutorError
from studymate.application.media.storage import (
    MediaObjectMissingError,
    MediaStorage,
    MediaStorageUnavailableError,
)
from studymate.domain.ai.jobs import Failure
from studymate.domain.media import MAX_PHOTO_BYTES, MediaObjectKind, MediaObjectRef


@dataclass(frozen=True, slots=True)
class RetainedDisplayReader:
    storage: MediaStorage

    async def display_image(self, reference: MediaObjectRef) -> bytes:
        # Ownership/version is rechecked in SQL; this port accepts only that private ref.
        if reference.kind != MediaObjectKind.DISPLAY:
            raise AiExecutorError(Failure.INVALID_INPUT)
        try:
            encoded = await self.storage.read(reference)
        except MediaObjectMissingError:
            raise AiExecutorError(Failure.INVALID_INPUT) from None
        except MediaStorageUnavailableError:
            raise AiExecutorError(Failure.TRANSIENT) from None
        if not 0 < len(encoded) <= MAX_PHOTO_BYTES or not encoded.startswith(b"\xff\xd8\xff"):
            raise AiExecutorError(Failure.INVALID_INPUT)
        return encoded
