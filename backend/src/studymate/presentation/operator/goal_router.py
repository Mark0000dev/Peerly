"""Mounted at actual67/head41; main owns public composition and export."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from studymate.application.operator.goals import ReadOperatorGoalHistory, ReadOperatorGoals
from studymate.presentation.browser import SESSION_AUTH, SESSION_COOKIE, read_cookie
from studymate.presentation.operator.goal_models import (
    OperatorGoalHistoryQuery,
    OperatorGoalHistoryResponse,
    OperatorGoalsQuery,
    OperatorGoalsResponse,
    goal_history_response,
    goals_response,
)
from studymate.presentation.operator.router import (
    OPERATOR_ERRORS,
    operator_problem,
    private_response,
)
from studymate.presentation.problems import ProblemResponse, problem


@dataclass(frozen=True, slots=True)
class OperatorGoalHttpServices:
    roots: ReadOperatorGoals
    history: ReadOperatorGoalHistory


def operator_goal_router(services: OperatorGoalHttpServices) -> APIRouter:
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

    @router.get("/accounts/{account_id}/goals", response_model=OperatorGoalsResponse)
    async def roots(
        request: Request,
        response: Response,
        account_id: UUID,
        query: Annotated[OperatorGoalsQuery, Query()],
    ) -> OperatorGoalsResponse | Response:
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
        return goals_response(page)

    @router.get(
        "/accounts/{account_id}/goals/{goal_id}/history", response_model=OperatorGoalHistoryResponse
    )
    async def history(
        request: Request,
        response: Response,
        account_id: UUID,
        goal_id: UUID,
        query: Annotated[OperatorGoalHistoryQuery, Query()],
    ) -> OperatorGoalHistoryResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            page = await services.history(credential, account_id, goal_id, query.cursor)
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        if page is None:
            return problem(HTTPStatus.NOT_FOUND, "operator_resource_unavailable")
        private_response(response)
        return goal_history_response(page)

    return router
