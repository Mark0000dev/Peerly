from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from math import ceil
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.browser import BrowserTokenSigner
from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.application.media.access import (
    CreatePhotoUploadAccess,
    PhotoUploadAccessDeniedError,
    ReadOwnPhotoDisplay,
)
from studymate.application.media.processing import InvalidImageError
from studymate.application.media.resume import RECENT_TERMINAL_UPLOADS, ReadOwnPhotoResume
from studymate.application.media.storage import (
    MediaObjectMissingError,
    MediaStorageUnavailableError,
    MediaUploadAccessExpiredError,
)
from studymate.application.media.uploads import (
    MAX_PENDING_UPLOADS,
    ChangePhotoUpload,
    PhotoUploadCommand,
    PhotoUploadRateLimitedError,
    PhotoUploadUnavailableError,
    PhotoVersionConflictError,
    ReadOwnPhotoUpload,
    StartPhotoCommand,
    StartPhotoUpload,
    UploadAction,
)
from studymate.domain.media import (
    MAX_PHOTO_BYTES,
    PhotoContentType,
    PhotoFailure,
    PhotoSource,
    PhotoUpload,
    PhotoUploadState,
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
from studymate.presentation.problems import ProblemResponse, problem
from studymate.presentation.profile_models import CurrentPhotoResponse
from studymate.presentation.student_errors import student_problem

MEDIA_ERRORS = (
    UnauthenticatedError,
    StudentActionDeniedError,
    PhotoUploadUnavailableError,
    PhotoVersionConflictError,
    IdempotencyConflictError,
    PhotoUploadAccessDeniedError,
    MediaUploadAccessExpiredError,
    MediaStorageUnavailableError,
    MediaObjectMissingError,
    InvalidImageError,
    PhotoUploadRateLimitedError,
)
POLL_AFTER_MS = 1000


@dataclass(frozen=True, slots=True)
class MediaServices:
    start: StartPhotoUpload
    change: ChangePhotoUpload
    read: ReadOwnPhotoUpload
    resume: ReadOwnPhotoResume
    access: CreatePhotoUploadAccess
    display: ReadOwnPhotoDisplay
    signer: BrowserTokenSigner
    browser: BrowserConfiguration


class StartPhotoRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    size_bytes: int = Field(strict=True, ge=1, le=MAX_PHOTO_BYTES)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    content_type: PhotoContentType
    expected_photo_version: int = Field(strict=True, ge=0)


class PhotoUploadResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID
    version: int
    state: PhotoUploadState
    size_bytes: int
    content_type: PhotoContentType
    expected_photo_version: int
    upload_expires_at: datetime
    processing_expires_at: datetime
    updated_at: datetime
    failure: PhotoFailure | None
    display_url: str | None
    poll_after_ms: int | None


class PhotoResumeItemResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    upload: PhotoUploadResponse
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)


class OwnPhotoResumeResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    photo: CurrentPhotoResponse | None
    uploads: tuple[PhotoResumeItemResponse, ...] = Field(
        max_length=MAX_PENDING_UPLOADS + RECENT_TERMINAL_UPLOADS + 1
    )


class UploadAccessResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    url: str = Field(repr=False)
    fields: dict[str, str] = Field(repr=False)


def _response(value: PhotoUpload) -> PhotoUploadResponse:
    return PhotoUploadResponse(
        id=value.id,
        version=value.version,
        state=value.state,
        size_bytes=value.source.size,
        content_type=value.source.content_type,
        expected_photo_version=value.expected_photo_version,
        upload_expires_at=value.upload_expires_at,
        processing_expires_at=value.processing_expires_at,
        updated_at=value.updated_at,
        failure=value.failure,
        display_url=f"/api/v1/media/{value.id}/display"
        if value.state == PhotoUploadState.READY
        else None,
        poll_after_ms=POLL_AFTER_MS if value.pending else None,
    )


_SIMPLE_ERRORS: tuple[tuple[type[Exception], HTTPStatus, str], ...] = (
    (PhotoUploadUnavailableError, HTTPStatus.NOT_FOUND, "photo_upload_unavailable"),
    (PhotoUploadAccessDeniedError, HTTPStatus.CONFLICT, "upload_not_uploading"),
    (MediaUploadAccessExpiredError, HTTPStatus.CONFLICT, "upload_expired"),
    (MediaStorageUnavailableError, HTTPStatus.SERVICE_UNAVAILABLE, "media_storage_unavailable"),
    (MediaObjectMissingError, HTTPStatus.SERVICE_UNAVAILABLE, "media_storage_unavailable"),
    (InvalidImageError, HTTPStatus.SERVICE_UNAVAILABLE, "media_storage_unavailable"),
)


def _error(error: Exception) -> JSONResponse:
    shared = student_problem(error)
    if shared is not None:
        return shared
    for kind, status, code in _SIMPLE_ERRORS:
        if isinstance(error, kind):
            return problem(status, code)
    if isinstance(error, PhotoVersionConflictError):
        return problem(
            HTTPStatus.CONFLICT,
            "photo_version_conflict",
            {"current_version": error.current_version},
        )
    if isinstance(error, PhotoUploadRateLimitedError):
        response = problem(
            HTTPStatus.TOO_MANY_REQUESTS,
            "photo_upload_rate_limited",
            {"retry_at": error.retry_at.isoformat()},
        )
        response.headers["Retry-After"] = str(
            max(1, ceil((error.retry_at - datetime.now(UTC)).total_seconds()))
        )
        return response
    raise error


async def _change(
    services: MediaServices,
    request: Request,
    headers: IdempotentWriteHeaders,
    upload_id: UUID,
    action: UploadAction,
) -> PhotoUploadResponse | Response:
    credential = await write_credential(request, services.signer, services.browser, headers)
    if isinstance(credential, JSONResponse):
        return credential
    try:
        result = await services.change(
            PhotoUploadCommand(credential, upload_id, action, IntentKey(headers.idempotency_key))
        )
    except MEDIA_ERRORS as error:
        return _error(error)
    return _response(result)


def media_router(services: MediaServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1",
        tags=["media"],
        dependencies=[SESSION_AUTH],
        responses={
            status.value: {"model": ProblemResponse}
            for status in (
                HTTPStatus.BAD_REQUEST,
                HTTPStatus.UNAUTHORIZED,
                HTTPStatus.FORBIDDEN,
                HTTPStatus.NOT_FOUND,
                HTTPStatus.CONFLICT,
                HTTPStatus.REQUEST_TIMEOUT,
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                HTTPStatus.UNPROCESSABLE_ENTITY,
                HTTPStatus.TOO_MANY_REQUESTS,
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        },
    )

    @router.get("/media/uploads", response_model=OwnPhotoResumeResponse)
    async def resume(request: Request, response: Response) -> OwnPhotoResumeResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.resume(credential)
        except MEDIA_ERRORS as error:
            return _error(error)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return OwnPhotoResumeResponse(
            photo=CurrentPhotoResponse(
                upload_id=result.photo.upload_id,
                version=result.photo.version,
                display_url=f"/api/v1/media/{result.photo.upload_id}/display",
            )
            if result.photo is not None
            else None,
            uploads=tuple(
                PhotoResumeItemResponse(
                    upload=_response(upload), source_sha256=upload.source.sha256.hex()
                )
                for upload in result.uploads
            ),
        )

    @router.post(
        "/media/uploads", status_code=HTTPStatus.ACCEPTED, response_model=PhotoUploadResponse
    )
    async def start(
        request: Request,
        body: StartPhotoRequest,
        response: Response,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> PhotoUploadResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            result = await services.start(
                StartPhotoCommand(
                    credential,
                    PhotoSource(body.size_bytes, bytes.fromhex(body.sha256), body.content_type),
                    body.expected_photo_version,
                    IntentKey(headers.idempotency_key),
                )
            )
        except MEDIA_ERRORS as error:
            return _error(error)
        response.headers["Cache-Control"] = "no-store"
        return _response(result)

    @router.post("/media/uploads/{upload_id}/access", response_model=UploadAccessResponse)
    async def access(
        request: Request,
        upload_id: UUID,
        response: Response,
        headers: Annotated[BrowserWriteHeaders, Header()],
    ) -> UploadAccessResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            result = await services.access(credential, upload_id)
        except MEDIA_ERRORS as error:
            return _error(error)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return UploadAccessResponse(url=result.url, fields=dict(result.fields))

    @router.post(
        "/media/uploads/{upload_id}/finalize",
        status_code=HTTPStatus.ACCEPTED,
        response_model=PhotoUploadResponse,
    )
    async def finalize(
        request: Request,
        upload_id: UUID,
        response: Response,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> PhotoUploadResponse | Response:
        response.headers["Cache-Control"] = "no-store"
        return await _change(services, request, headers, upload_id, UploadAction.FINALIZE)

    @router.post("/media/uploads/{upload_id}/cancel", response_model=PhotoUploadResponse)
    async def cancel(
        request: Request,
        upload_id: UUID,
        response: Response,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> PhotoUploadResponse | Response:
        response.headers["Cache-Control"] = "no-store"
        return await _change(services, request, headers, upload_id, UploadAction.CANCEL)

    @router.get("/media/{upload_id}", response_model=PhotoUploadResponse)
    async def status(
        request: Request, upload_id: UUID, response: Response
    ) -> PhotoUploadResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.read(credential, upload_id)
        except MEDIA_ERRORS as error:
            return _error(error)
        response.headers["Cache-Control"] = "no-store"
        return _response(result)

    @router.get(
        "/media/{upload_id}/display",
        response_class=Response,
        responses={
            HTTPStatus.OK.value: {
                "content": {"image/jpeg": {"schema": {"type": "string", "format": "binary"}}}
            }
        },
    )
    async def display(request: Request, upload_id: UUID) -> Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            data = await services.display(credential, upload_id)
        except MEDIA_ERRORS as error:
            return _error(error)
        return Response(
            data,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
            },
        )

    return router
