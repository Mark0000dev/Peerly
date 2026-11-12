"""Lifecycle history factory, locally mounted by main with existing READ_ACCOUNT authority."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from studymate.application.operator.lifecycle_history import ReadOperatorLifecycleHistory
from studymate.presentation.browser import SESSION_AUTH, SESSION_COOKIE, read_cookie
from studymate.presentation.operator.lifecycle_history_models import (
    OperatorLifecycleHistoryQuery,
    OperatorLifecycleHistoryResponse,
    lifecycle_history_response,
)
from studymate.presentation.operator.router import (
    OPERATOR_ERRORS,
    operator_problem,
    private_response,
)
from studymate.presentation.problems import ProblemResponse, problem


@dataclass(frozen=True, slots=True)
class OperatorLifecycleHistoryHttpServices:
    history: ReadOperatorLifecycleHistory


def operator_lifecycle_history_router(services: OperatorLifecycleHistoryHttpServices) -> APIRouter:
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
        "/accounts/{account_id}/lifecycle-history", response_model=OperatorLifecycleHistoryResponse
    )
    async def history(
        request: Request,
        response: Response,
        account_id: UUID,
        query: Annotated[OperatorLifecycleHistoryQuery, Query()],
    ) -> OperatorLifecycleHistoryResponse | Response:
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
        return lifecycle_history_response(page)

    return router
