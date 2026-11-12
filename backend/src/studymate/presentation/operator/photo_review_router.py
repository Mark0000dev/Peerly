"""Explicit human commands and separate owner-only recovery; no automatic sanctions."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response
from starlette.responses import JSONResponse

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.browser import BrowserTokenSigner
from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.application.operator.photo_review import (
    PhotoReviewApprovalConflictError,
    PhotoReviewUnavailableError,
    PhotoReviewVersionConflictError,
    ReadPhotoReviewContext,
    ReviewPhoto,
    ReviewPhotoCommand,
)
from studymate.application.profiles.photo_review import ReadOwnPhotoReview
from studymate.presentation.browser import (
    SESSION_AUTH,
    SESSION_COOKIE,
    BrowserConfiguration,
    IdempotentWriteHeaders,
    read_cookie,
    write_credential,
)
from studymate.presentation.operator.photo_review_models import (
    OwnPhotoReviewResponse,
    PhotoReviewBody,
    PhotoReviewContextResponse,
    PhotoReviewResponse,
    own_photo_review_response,
    photo_review_context,
    photo_review_response,
)
from studymate.presentation.operator.router import (
    OPERATOR_ERRORS,
    operator_problem,
    private_response,
)
from studymate.presentation.problems import ProblemResponse, problem


@dataclass(frozen=True, slots=True)
class PhotoReviewHttpServices:
    context: ReadPhotoReviewContext
    review: ReviewPhoto
    signer: BrowserTokenSigner
    browser: BrowserConfiguration


def operator_photo_review_router(services: PhotoReviewHttpServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/operator/accounts",
        tags=["operator"],
        dependencies=[SESSION_AUTH],
        responses={
            code: {"model": ProblemResponse} for code in (401, 403, 404, 409, 413, 415, 422, 503)
        },
    )

    @router.get("/{account_id}/photo-review", response_model=PhotoReviewContextResponse)
    async def context(
        account_id: UUID, request: Request, response: Response
    ) -> PhotoReviewContextResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            target = await services.context(credential, account_id)
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        if target is None:
            return problem(HTTPStatus.NOT_FOUND, "operator_resource_unavailable")
        private_response(response)
        return photo_review_context(target)

    @router.post("/{account_id}/photo-reviews", response_model=PhotoReviewResponse)
    async def review(
        account_id: UUID,
        body: PhotoReviewBody,
        request: Request,
        response: Response,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> PhotoReviewResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            source = await services.review(
                ReviewPhotoCommand(
                    credential,
                    account_id,
                    body.expected_version,
                    body.expected_photo_version,
                    body.expected_upload_id,
                    body.action,
                    body.reason,
                    IntentKey(headers.idempotency_key),
                )
            )
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        except PhotoReviewUnavailableError:
            return problem(HTTPStatus.NOT_FOUND, "photo_review_unavailable")
        except (
            PhotoReviewVersionConflictError,
            PhotoReviewApprovalConflictError,
            IdempotencyConflictError,
        ) as error:
            code = (
                "photo_review_version_conflict"
                if isinstance(error, PhotoReviewVersionConflictError)
                else "photo_review_approval_conflict"
                if isinstance(error, PhotoReviewApprovalConflictError)
                else "idempotency_conflict"
            )
            return problem(HTTPStatus.CONFLICT, code)
        private_response(response)
        return photo_review_response(source)

    return router


def own_photo_review_router(read: ReadOwnPhotoReview) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/me",
        tags=["profile"],
        dependencies=[SESSION_AUTH],
        responses={code: {"model": ProblemResponse} for code in (401, 403, 503)},
    )

    @router.get("/photo-review", response_model=OwnPhotoReviewResponse)
    async def recovery(request: Request, response: Response) -> OwnPhotoReviewResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            source = await read(credential)
        except UnauthenticatedError:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        except StudentActionDeniedError:
            return problem(HTTPStatus.FORBIDDEN, "student_action_not_allowed")
        private_response(response)
        return own_photo_review_response(source)

    return router
