"""Unmounted retained chat-image metadata factory; main owns composition/export."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from studymate.application.operator.chat_image_uploads import (
    ReadOperatorChatImageHistory,
    ReadOperatorChatImageUploads,
)
from studymate.presentation.browser import SESSION_AUTH, SESSION_COOKIE, read_cookie
from studymate.presentation.operator.chat_image_models import (
    OperatorChatImageHistoryQuery,
    OperatorChatImageHistoryResponse,
    OperatorChatImageUploadsQuery,
    OperatorChatImageUploadsResponse,
    chat_image_history_response,
    chat_image_uploads_response,
)
from studymate.presentation.operator.router import (
    OPERATOR_ERRORS,
    operator_problem,
    private_response,
)
from studymate.presentation.problems import ProblemResponse, problem


@dataclass(frozen=True, slots=True)
class OperatorChatImageHttpServices:
    roots: ReadOperatorChatImageUploads
    history: ReadOperatorChatImageHistory


def operator_chat_image_router(services: OperatorChatImageHttpServices) -> APIRouter:
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

    @router.get(
        "/accounts/{account_id}/chat-image-uploads", response_model=OperatorChatImageUploadsResponse
    )
    async def roots(
        request: Request,
        response: Response,
        account_id: UUID,
        query: Annotated[OperatorChatImageUploadsQuery, Query()],
    ) -> OperatorChatImageUploadsResponse | Response:
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
        return chat_image_uploads_response(page)

    @router.get(
        "/accounts/{account_id}/chat-image-uploads/{image_id}/history",
        response_model=OperatorChatImageHistoryResponse,
    )
    async def history(
        request: Request,
        response: Response,
        account_id: UUID,
        image_id: UUID,
        query: Annotated[OperatorChatImageHistoryQuery, Query()],
    ) -> OperatorChatImageHistoryResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            page = await services.history(credential, account_id, image_id, query.cursor)
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        if page is None:
            return problem(HTTPStatus.NOT_FOUND, "operator_resource_unavailable")
        private_response(response)
        return chat_image_history_response(page)

    return router
