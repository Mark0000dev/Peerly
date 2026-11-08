"""Mounted at actual70/head43; retained photo metadata, main-owned composition."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from studymate.application.operator.photo_uploads import (
    ReadOperatorPhotoHistory,
    ReadOperatorPhotoUploads,
)
from studymate.presentation.browser import SESSION_AUTH, SESSION_COOKIE, read_cookie
from studymate.presentation.operator.photo_models import (
    OperatorPhotoHistoryQuery,
    OperatorPhotoHistoryResponse,
    OperatorPhotoUploadsQuery,
    OperatorPhotoUploadsResponse,
    photo_history_response,
    photo_uploads_response,
)
from studymate.presentation.operator.router import (
    OPERATOR_ERRORS,
    operator_problem,
    private_response,
)
from studymate.presentation.problems import ProblemResponse, problem


@dataclass(frozen=True, slots=True)
class OperatorPhotoHttpServices:
    roots: ReadOperatorPhotoUploads
    history: ReadOperatorPhotoHistory


def operator_photo_router(services: OperatorPhotoHttpServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/operator",
        tags=["operator"],
        dependencies=[SESSION_AUTH],
        responses={
            status.value: {"model": ProblemResponse}
            for status in (
                HTTPStatus.UNAUTHORIZED,
                HTTPStatus.FORBIDDEN,
                HTTPStatus.NOT_FOUND,
                HTTPStatus.UNPROCESSABLE_ENTITY,
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        },
    )

    @router.get("/accounts/{account_id}/photo-uploads", response_model=OperatorPhotoUploadsResponse)
    async def roots(
        request: Request,
        response: Response,
        account_id: UUID,
        query: Annotated[OperatorPhotoUploadsQuery, Query()],
    ) -> OperatorPhotoUploadsResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            page = await services.roots(credential, account_id, query.filters(), query.cursor)
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        if page is None:
            return problem(HTTPStatus.NOT_FOUND, "operator_resource_unavailable")
        private_response(response)
        return photo_uploads_response(page)

    @router.get(
        "/accounts/{account_id}/photo-uploads/{upload_id}/history",
        response_model=OperatorPhotoHistoryResponse,
    )
    async def history(
        request: Request,
        response: Response,
        account_id: UUID,
        upload_id: UUID,
        query: Annotated[OperatorPhotoHistoryQuery, Query()],
    ) -> OperatorPhotoHistoryResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            page = await services.history(credential, account_id, upload_id, query.cursor)
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        if page is None:
            return problem(HTTPStatus.NOT_FOUND, "operator_resource_unavailable")
        private_response(response)
        return photo_history_response(page)

    return router
