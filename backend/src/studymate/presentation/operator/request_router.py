"""Unmounted privileged retained connection-request factories; no Requests state/ACK writes."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from studymate.application.operator.connection_requests import (
    ReadOperatorRequestHistory,
    ReadOperatorRequests,
)
from studymate.presentation.browser import SESSION_AUTH, SESSION_COOKIE, read_cookie
from studymate.presentation.operator.request_models import (
    OperatorRequestHistoryQuery,
    OperatorRequestHistoryResponse,
    OperatorRequestsQuery,
    OperatorRequestsResponse,
    request_history_response,
    requests_response,
)
from studymate.presentation.operator.router import (
    OPERATOR_ERRORS,
    operator_problem,
    private_response,
)
from studymate.presentation.problems import ProblemResponse, problem


@dataclass(frozen=True, slots=True)
class OperatorRequestHttpServices:
    requests: ReadOperatorRequests
    history: ReadOperatorRequestHistory


def operator_request_router(services: OperatorRequestHttpServices) -> APIRouter:
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
        "/accounts/{account_id}/connection-requests", response_model=OperatorRequestsResponse
    )
    async def requests(
        request: Request,
        response: Response,
        account_id: UUID,
        query: Annotated[OperatorRequestsQuery, Query()],
    ) -> OperatorRequestsResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            page = await services.requests(credential, account_id, query.filters(), query.cursor)
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        if page is None:
            return problem(HTTPStatus.NOT_FOUND, "operator_resource_unavailable")
        private_response(response)
        return requests_response(page)

    @router.get(
        "/accounts/{account_id}/connection-requests/{request_id}/history",
        response_model=OperatorRequestHistoryResponse,
    )
    async def history(
        request: Request,
        response: Response,
        account_id: UUID,
        request_id: UUID,
        query: Annotated[OperatorRequestHistoryQuery, Query()],
    ) -> OperatorRequestHistoryResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            page = await services.history(credential, account_id, request_id, query.cursor)
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        if page is None:
            return problem(HTTPStatus.NOT_FOUND, "operator_resource_unavailable")
        private_response(response)
        return request_history_response(page)

    return router
