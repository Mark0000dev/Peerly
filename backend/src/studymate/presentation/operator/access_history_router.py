"""Operator-access history factory, locally mounted by main with existing READ_ACCOUNT authority."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from studymate.application.operator.access_history import ReadOperatorAccessHistory
from studymate.presentation.browser import SESSION_AUTH, SESSION_COOKIE, read_cookie
from studymate.presentation.operator.access_history_models import (
    OperatorAccessHistoryQuery,
    OperatorAccessHistoryResponse,
    access_history_response,
)
from studymate.presentation.operator.router import (
    OPERATOR_ERRORS,
    operator_problem,
    private_response,
)
from studymate.presentation.problems import ProblemResponse, problem


@dataclass(frozen=True, slots=True)
class OperatorAccessHistoryHttpServices:
    history: ReadOperatorAccessHistory


def operator_access_history_router(services: OperatorAccessHistoryHttpServices) -> APIRouter:
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
        "/accounts/{account_id}/operator-access-history",
        response_model=OperatorAccessHistoryResponse,
    )
    async def history(
        request: Request,
        response: Response,
        account_id: UUID,
        query: Annotated[OperatorAccessHistoryQuery, Query()],
    ) -> OperatorAccessHistoryResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            page = await services.history(credential, account_id, query.cursor)
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        if page is None:
            return problem(HTTPStatus.NOT_FOUND, "operator_resource_unavailable")
        private_response(response)
        return access_history_response(page)

    return router
