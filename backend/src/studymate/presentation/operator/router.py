"""Unmounted operator read factory; main owns role provisioning and composition."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from starlette.responses import JSONResponse

from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.accounts import ReadOperatorAccount, SearchOperatorAccounts
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.cursors import InvalidOperatorCursorError
from studymate.application.operator.messages import ReadOperatorConversationMessages
from studymate.presentation.browser import SESSION_AUTH, SESSION_COOKIE, read_cookie
from studymate.presentation.operator.models import (
    AccountSearchQuery,
    OperatorAccountDetailResponse,
    OperatorAccountsResponse,
    OperatorMessagesResponse,
    accounts_response,
    detail_response,
    messages_response,
)
from studymate.presentation.problems import ProblemResponse, problem

OPERATOR_ERRORS = (
    UnauthenticatedError,
    OperatorAccessDeniedError,
    InvalidOperatorCursorError,
    StorageUnavailableError,
)


@dataclass(frozen=True, slots=True)
class OperatorHttpServices:
    search: SearchOperatorAccounts
    account: ReadOperatorAccount
    messages: ReadOperatorConversationMessages


def operator_problem(error: Exception) -> JSONResponse:
    if isinstance(error, StorageUnavailableError):
        response = problem(HTTPStatus.SERVICE_UNAVAILABLE, "storage_unavailable")
        response.headers["Retry-After"] = "1"
        return response
    for kind, status, code in (
        (UnauthenticatedError, HTTPStatus.UNAUTHORIZED, "unauthenticated"),
        (OperatorAccessDeniedError, HTTPStatus.FORBIDDEN, "operator_access_denied"),
        (InvalidOperatorCursorError, HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_operator_cursor"),
    ):
        if isinstance(error, kind):
            return problem(status, code)
    raise error


def private_response(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"


def operator_router(services: OperatorHttpServices) -> APIRouter:
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

    @router.get("/accounts", response_model=OperatorAccountsResponse)
    async def search(
        request: Request,
        response: Response,
        query: Annotated[AccountSearchQuery, Query()],
    ) -> OperatorAccountsResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.search(credential, query.filters(), query.cursor)
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        private_response(response)
        return accounts_response(result)

    @router.get("/accounts/{account_id}", response_model=OperatorAccountDetailResponse)
    async def account(
        request: Request, response: Response, account_id: UUID
    ) -> OperatorAccountDetailResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.account(credential, account_id)
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        if result is None:
            return problem(HTTPStatus.NOT_FOUND, "operator_resource_unavailable")
        private_response(response)
        return detail_response(result)

    @router.get(
        "/conversations/{conversation_id}/messages", response_model=OperatorMessagesResponse
    )
    async def messages(
        request: Request,
        response: Response,
        conversation_id: UUID,
        cursor: Annotated[str | None, Query(min_length=1, max_length=1024)] = None,
    ) -> OperatorMessagesResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.messages(credential, conversation_id, cursor)
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        if result is None:
            return problem(HTTPStatus.NOT_FOUND, "operator_resource_unavailable")
        private_response(response)
        return messages_response(result)

    return router
