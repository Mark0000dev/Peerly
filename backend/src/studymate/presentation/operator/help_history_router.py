"""Mounted at actual67/head41; existing READ_ACCOUNT authority/audit only."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from studymate.application.operator.help_history import ReadOperatorHelpHistory
from studymate.presentation.browser import SESSION_AUTH, SESSION_COOKIE, read_cookie
from studymate.presentation.operator.help_history_models import (
    OperatorHelpHistoryQuery,
    OperatorHelpHistoryResponse,
    help_history_response,
)
from studymate.presentation.operator.router import (
    OPERATOR_ERRORS,
    operator_problem,
    private_response,
)
from studymate.presentation.problems import ProblemResponse, problem


@dataclass(frozen=True, slots=True)
class OperatorHelpHistoryHttpServices:
    history: ReadOperatorHelpHistory


def operator_help_history_router(services: OperatorHelpHistoryHttpServices) -> APIRouter:
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

    @router.get("/accounts/{account_id}/help-history", response_model=OperatorHelpHistoryResponse)
    async def history(
        request: Request,
        response: Response,
        account_id: UUID,
        query: Annotated[OperatorHelpHistoryQuery, Query()],
    ) -> OperatorHelpHistoryResponse | Response:
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
        return help_history_response(page)

    return router
