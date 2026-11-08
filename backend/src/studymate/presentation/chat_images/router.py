"""Only an explicit message send publishes a processed image to a conversation."""

from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from math import ceil
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response
from starlette.responses import JSONResponse

from studymate.application.chat_images.access import (
    ChatImageUploadAccessDeniedError,
    CreateChatImageUploadAccess,
)
from studymate.application.chat_images.display import ReadMessageImageDisplay, ReadOwnedImageDisplay
from studymate.application.chat_images.finalize import (
    ChatImageUnavailableError,
    FinalizeChatImage,
    FinalizeChatImageCommand,
)
from studymate.application.chat_images.reads import (
    ListOwnImagePreparations,
    ReadOwnedImagePreparation,
)
from studymate.application.chat_images.start import (
    ChatImageMessageResolvedError,
    ChatImageRateLimitedError,
    ChatImageSourceConflictError,
    StartChatImage,
    StartChatImageCommand,
)
from studymate.application.errors import StorageUnavailableError
from studymate.application.idempotency import IntentKey
from studymate.application.identity.browser import BrowserTokenSigner
from studymate.application.media.storage import (
    MediaStorageUnavailableError,
    MediaUploadAccessExpiredError,
)
from studymate.application.messaging.ports import (
    ConversationUnavailableError,
    MessageContactUnavailableError,
)
from studymate.presentation.browser import (
    SESSION_AUTH,
    SESSION_COOKIE,
    BrowserConfiguration,
    BrowserWriteHeaders,
    IdempotentWriteHeaders,
    read_cookie,
    write_credential,
)
from studymate.presentation.chat_images.models import (
    ImagePreparationReceipt,
    ImagePreparationResponse,
    ImagePreparationsResponse,
    ImageUploadAccessResponse,
    StartImageBody,
    image_receipt,
    image_response,
)
from studymate.presentation.problems import ProblemResponse, problem
from studymate.presentation.student_errors import STUDENT_ERRORS, student_problem

IMAGE_ERRORS = (
    *STUDENT_ERRORS,
    ChatImageMessageResolvedError,
    ChatImageRateLimitedError,
    ChatImageSourceConflictError,
    ChatImageUnavailableError,
    ChatImageUploadAccessDeniedError,
    ConversationUnavailableError,
    MessageContactUnavailableError,
    StorageUnavailableError,
    MediaStorageUnavailableError,
    MediaUploadAccessExpiredError,
)


@dataclass(frozen=True, slots=True)
class ChatImageHttpServices:
    start: StartChatImage
    finalize: FinalizeChatImage
    read: ReadOwnedImagePreparation
    recovery: ListOwnImagePreparations
    access: CreateChatImageUploadAccess
    own_display: ReadOwnedImageDisplay
    message_display: ReadMessageImageDisplay
    signer: BrowserTokenSigner
    browser: BrowserConfiguration


def image_problem(error: Exception) -> JSONResponse:
    shared = student_problem(error)
    if shared is not None:
        return shared
    if isinstance(error, (StorageUnavailableError, MediaStorageUnavailableError)):
        response = problem(HTTPStatus.SERVICE_UNAVAILABLE, "image_unavailable")
        response.headers["Retry-After"] = "1"
        return response
    if isinstance(error, ChatImageRateLimitedError):
        response = problem(
            HTTPStatus.TOO_MANY_REQUESTS,
            "image_rate_limited",
            {"retry_at": error.retry_at.isoformat()},
        )
        response.headers["Retry-After"] = str(
            max(1, ceil((error.retry_at - datetime.now(UTC)).total_seconds()))
        )
        return response
    if isinstance(error, ChatImageMessageResolvedError):
        operation = error.operation
        return problem(
            HTTPStatus.CONFLICT,
            "image_message_resolved",
            {
                "operation_id": str(operation.id),
                "outcome": operation.outcome.value,
                "client_message_id": str(operation.client_message_id),
                "message_id": str(operation.message.id) if operation.message is not None else None,
            },
        )
    for kind, status, code in (
        (ChatImageUnavailableError, HTTPStatus.NOT_FOUND, "image_unavailable"),
        (ConversationUnavailableError, HTTPStatus.NOT_FOUND, "conversation_unavailable"),
        (ChatImageSourceConflictError, HTTPStatus.CONFLICT, "image_source_conflict"),
        (MessageContactUnavailableError, HTTPStatus.CONFLICT, "message_contact_unavailable"),
        (ChatImageUploadAccessDeniedError, HTTPStatus.CONFLICT, "image_upload_closed"),
        (MediaUploadAccessExpiredError, HTTPStatus.CONFLICT, "image_upload_closed"),
    ):
        if isinstance(error, kind):
            return problem(status, code)
    raise error


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"


def _display(data: bytes, content_type: str) -> Response:
    response = Response(data, media_type=content_type)
    _private(response)
    response.headers["Content-Disposition"] = 'inline; filename="image.jpg"'
    response.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return response


def chat_image_router(services: ChatImageHttpServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/conversations",
        tags=["chat-images"],
        dependencies=[SESSION_AUTH],
        responses={
            status.value: {"model": ProblemResponse}
            for status in (
                HTTPStatus.UNAUTHORIZED,
                HTTPStatus.FORBIDDEN,
                HTTPStatus.NOT_FOUND,
                HTTPStatus.CONFLICT,
                HTTPStatus.UNPROCESSABLE_ENTITY,
                HTTPStatus.TOO_MANY_REQUESTS,
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        },
    )

    @router.post(
        "/{conversation_id}/image-preparations",
        response_model=ImagePreparationReceipt,
        status_code=HTTPStatus.ACCEPTED,
    )
    async def start(
        request: Request,
        response: Response,
        conversation_id: UUID,
        body: StartImageBody,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> ImagePreparationReceipt | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            result = await services.start(
                StartChatImageCommand(
                    credential,
                    conversation_id,
                    body.client_message_id,
                    body.source(),
                    IntentKey(headers.idempotency_key),
                )
            )
        except IMAGE_ERRORS as error:
            return image_problem(error)
        _private(response)
        return image_receipt(result)

    @router.get("/{conversation_id}/image-preparations", response_model=ImagePreparationsResponse)
    async def recover(
        request: Request, response: Response, conversation_id: UUID
    ) -> ImagePreparationsResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.recovery(credential, conversation_id)
        except IMAGE_ERRORS as error:
            return image_problem(error)
        _private(response)
        return ImagePreparationsResponse(
            preparations=tuple(image_response(value) for value in result)
        )

    @router.get(
        "/{conversation_id}/image-preparations/{image_id}", response_model=ImagePreparationResponse
    )
    async def read(
        request: Request, response: Response, conversation_id: UUID, image_id: UUID
    ) -> ImagePreparationResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.read(credential, conversation_id, image_id)
        except IMAGE_ERRORS as error:
            return image_problem(error)
        _private(response)
        return image_response(result)

    @router.post(
        "/{conversation_id}/image-preparations/{image_id}/upload-access",
        response_model=ImageUploadAccessResponse,
    )
    async def access(
        request: Request,
        response: Response,
        conversation_id: UUID,
        image_id: UUID,
        headers: Annotated[BrowserWriteHeaders, Header()],
    ) -> ImageUploadAccessResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            result = await services.access(credential, conversation_id, image_id)
        except IMAGE_ERRORS as error:
            return image_problem(error)
        _private(response)
        return ImageUploadAccessResponse(url=result.url, fields=dict(result.fields))

    @router.post(
        "/{conversation_id}/image-preparations/{image_id}/finalize",
        response_model=ImagePreparationReceipt,
        status_code=HTTPStatus.ACCEPTED,
    )
    async def finalize(
        request: Request,
        response: Response,
        conversation_id: UUID,
        image_id: UUID,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> ImagePreparationReceipt | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            result = await services.finalize(
                FinalizeChatImageCommand(
                    credential,
                    conversation_id,
                    image_id,
                    IntentKey(headers.idempotency_key),
                )
            )
        except IMAGE_ERRORS as error:
            return image_problem(error)
        _private(response)
        return image_receipt(result)

    @router.get(
        "/{conversation_id}/image-preparations/{image_id}/display",
        responses={
            200: {"content": {"image/jpeg": {"schema": {"type": "string", "format": "binary"}}}}
        },
        response_class=Response,
    )
    async def own_display(request: Request, conversation_id: UUID, image_id: UUID) -> Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.own_display(credential, conversation_id, image_id)
        except IMAGE_ERRORS as error:
            return image_problem(error)
        return _display(result.data, result.content_type)

    @router.get(
        "/{conversation_id}/messages/{message_id}/image",
        responses={
            200: {"content": {"image/jpeg": {"schema": {"type": "string", "format": "binary"}}}}
        },
        response_class=Response,
    )
    async def message_display(
        request: Request, conversation_id: UUID, message_id: UUID
    ) -> Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.message_display(credential, conversation_id, message_id)
        except IMAGE_ERRORS as error:
            return image_problem(error)
        return _display(result.data, result.content_type)

    return router
