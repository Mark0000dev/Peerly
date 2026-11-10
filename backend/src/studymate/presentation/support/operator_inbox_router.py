from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from studymate.application.support.operator_inbox import (
    ReadOperatorSupportHistory,
    SearchOperatorSupportCases,
)
from studymate.presentation.browser import SESSION_AUTH, SESSION_COOKIE, read_cookie
from studymate.presentation.operator.router import (
    OPERATOR_ERRORS,
    operator_problem,
    private_response,
)
from studymate.presentation.problems import ProblemResponse, problem
from studymate.presentation.support.operator_inbox_models import (
    OperatorSupportHistoryQuery,
    OperatorSupportHistoryResponse,
    OperatorSupportInboxQuery,
    OperatorSupportInboxResponse,
    history_response,
    inbox_response,
)


@dataclass(frozen=True, slots=True)
class OperatorSupportInboxHttpServices:
    search: SearchOperatorSupportCases
    history: ReadOperatorSupportHistory


def operator_support_inbox_router(services: OperatorSupportInboxHttpServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/operator/cases",
        tags=["operator"],
        dependencies=[SESSION_AUTH],
        responses={code: {"model": ProblemResponse} for code in (401, 403, 404, 422, 503)},
    )

    @router.get("", response_model=OperatorSupportInboxResponse)
    async def search(
        request: Request, response: Response, query: Annotated[OperatorSupportInboxQuery, Query()]
    ) -> OperatorSupportInboxResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.search(credential, query.filters(), query.cursor)
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        private_response(response)
        return inbox_response(result)

    @router.get("/{case_id}/history", response_model=OperatorSupportHistoryResponse)
    async def history(
        case_id: UUID,
        request: Request,
        response: Response,
        query: Annotated[OperatorSupportHistoryQuery, Query()],
    ) -> OperatorSupportHistoryResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.history(credential, case_id, query.cursor)
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        if result is None:
            return problem(HTTPStatus.NOT_FOUND, "operator_resource_unavailable")
        private_response(response)
        return history_response(result)

    return router
