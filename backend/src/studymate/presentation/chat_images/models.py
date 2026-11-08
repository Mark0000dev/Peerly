"""Owner source fingerprint is recovery metadata, never a storage credential or grant."""

from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from studymate.application.chat_images.reads import OWNED_IMAGE_LIMIT, OwnedImagePreparation
from studymate.domain.chat_images import ChatImageFailure, ChatImagePreparation, ChatImageState
from studymate.domain.media import MAX_PHOTO_BYTES, PhotoContentType, PhotoSource
from studymate.domain.messaging import MessageOutcome


class ClosedModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class StartImageBody(ClosedModel):
    client_message_id: UUID
    size: int = Field(strict=True, ge=1, le=MAX_PHOTO_BYTES)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    content_type: PhotoContentType

    def source(self) -> PhotoSource:
        return PhotoSource(self.size, bytes.fromhex(self.sha256), self.content_type)


class ImagePreparationReceipt(ClosedModel):
    image_id: UUID
    conversation_id: UUID
    client_message_id: UUID
    receipt_version: int = Field(ge=1)
    receipt_state: ChatImageState


class ExpectedImageSource(ClosedModel):
    size: int = Field(ge=1, le=MAX_PHOTO_BYTES)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    content_type: PhotoContentType


class ReadyImageMetadata(ClosedModel):
    width: int = Field(ge=1, le=1024)
    height: int = Field(ge=1, le=1024)
    size: int = Field(ge=1, le=MAX_PHOTO_BYTES)


class PreparationMessageOutcome(ClosedModel):
    operation_id: UUID
    outcome: MessageOutcome
    message_id: UUID | None
    attachment_confirmed: bool


class ImagePreparationResponse(ClosedModel):
    image_id: UUID
    conversation_id: UUID
    client_message_id: UUID
    source_version: int = Field(ge=1)
    source_state: ChatImageState
    state: ChatImageState
    failure: ChatImageFailure | None
    created_at: AwareDatetime
    updated_at: AwareDatetime
    upload_expires_at: AwareDatetime
    processing_expires_at: AwareDatetime
    expected_source: ExpectedImageSource = Field(repr=False)
    display: ReadyImageMetadata | None
    message_outcome: PreparationMessageOutcome | None


class ImagePreparationsResponse(ClosedModel):
    preparations: tuple[ImagePreparationResponse, ...] = Field(max_length=OWNED_IMAGE_LIMIT)


class ImageUploadAccessResponse(ClosedModel):
    url: str = Field(repr=False)
    fields: dict[str, str] = Field(repr=False)


def image_receipt(value: ChatImagePreparation) -> ImagePreparationReceipt:
    return ImagePreparationReceipt(
        image_id=value.id,
        conversation_id=value.conversation_id,
        client_message_id=value.client_message_id,
        receipt_version=value.version,
        receipt_state=value.state,
    )


def image_response(value: OwnedImagePreparation) -> ImagePreparationResponse:
    image, ready, outcome = value.preparation, value.ready, value.message_outcome
    return ImagePreparationResponse(
        image_id=image.id,
        conversation_id=image.conversation_id,
        client_message_id=image.client_message_id,
        source_version=image.version,
        source_state=image.state,
        state=value.effective_state,
        failure=image.failure,
        created_at=image.created_at,
        updated_at=image.updated_at,
        upload_expires_at=image.upload_expires_at,
        processing_expires_at=image.processing_expires_at,
        expected_source=ExpectedImageSource(
            size=image.source.size,
            sha256=image.source.sha256.hex(),
            content_type=image.source.content_type,
        ),
        display=ReadyImageMetadata(width=ready.width, height=ready.height, size=ready.size)
        if ready is not None
        else None,
        message_outcome=PreparationMessageOutcome(
            operation_id=outcome.id,
            outcome=outcome.outcome,
            message_id=outcome.message_id,
            attachment_confirmed=outcome.message_image_id == image.id,
        )
        if outcome is not None
        else None,
    )
