"""Unmounted retained peer-feedback inspection only; main composes the public API."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from studymate.application.operator.peer_feedback import (
    ReadOperatorFeedback,
    ReadOperatorFeedbackHistory,
    ReadOperatorFeedbackRemovals,
)
from studymate.presentation.browser import SESSION_AUTH, SESSION_COOKIE, read_cookie
from studymate.presentation.operator.feedback_models import (
    OperatorFeedbackChildQuery,
    OperatorFeedbackHistoryResponse,
    OperatorFeedbackQuery,
    OperatorFeedbackRemovalsResponse,
    OperatorFeedbackRootsResponse,
    feedback_history_response,
    feedback_removals_response,
    feedback_roots_response,
)
from studymate.presentation.operator.router import (
    OPERATOR_ERRORS,
    operator_problem,
    private_response,
)
from studymate.presentation.problems import ProblemResponse, problem


@dataclass(frozen=True, slots=True)
class OperatorFeedbackHttpServices:
    roots: ReadOperatorFeedback
    history: ReadOperatorFeedbackHistory
    removals: ReadOperatorFeedbackRemovals


def operator_feedback_router(services: OperatorFeedbackHttpServices) -> APIRouter:
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
        "/accounts/{account_id}/peer-feedback", response_model=OperatorFeedbackRootsResponse
    )
    async def roots(
        request: Request,
        response: Response,
        account_id: UUID,
        query: Annotated[OperatorFeedbackQuery, Query()],
    ) -> OperatorFeedbackRootsResponse | Response:
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
        return feedback_roots_response(page)

    @router.get(
        "/accounts/{account_id}/peer-feedback/{feedback_id}/history",
        response_model=OperatorFeedbackHistoryResponse,
    )
    async def history(
        request: Request,
        response: Response,
        account_id: UUID,
        feedback_id: UUID,
        query: Annotated[OperatorFeedbackChildQuery, Query()],
    ) -> OperatorFeedbackHistoryResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            page = await services.history(credential, account_id, feedback_id, query.cursor)
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        if page is None:
            return problem(HTTPStatus.NOT_FOUND, "operator_resource_unavailable")
        private_response(response)
        return feedback_history_response(page)

    @router.get(
        "/accounts/{account_id}/peer-feedback/{feedback_id}/removals",
        response_model=OperatorFeedbackRemovalsResponse,
    )
    async def removals(
        request: Request,
        response: Response,
        account_id: UUID,
        feedback_id: UUID,
        query: Annotated[OperatorFeedbackChildQuery, Query()],
    ) -> OperatorFeedbackRemovalsResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            page = await services.removals(credential, account_id, feedback_id, query.cursor)
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        if page is None:
            return problem(HTTPStatus.NOT_FOUND, "operator_resource_unavailable")
        private_response(response)
        return feedback_removals_response(page)

    return router
