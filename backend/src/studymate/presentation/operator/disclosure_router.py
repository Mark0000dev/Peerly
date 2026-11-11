"""Unmounted one-GET retained request disclosures; composition belongs to main backend."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from studymate.application.operator.request_disclosures import ReadOperatorRequestDisclosures
from studymate.presentation.browser import SESSION_AUTH, SESSION_COOKIE, read_cookie
from studymate.presentation.operator.disclosure_models import (
    OperatorDisclosuresQuery,
    OperatorDisclosuresResponse,
    disclosures_response,
)
from studymate.presentation.operator.router import (
    OPERATOR_ERRORS,
    operator_problem,
    private_response,
)
from studymate.presentation.problems import ProblemResponse, problem


@dataclass(frozen=True, slots=True)
class OperatorDisclosureHttpServices:
    disclosures: ReadOperatorRequestDisclosures


def operator_disclosure_router(services: OperatorDisclosureHttpServices) -> APIRouter:
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
        "/accounts/{account_id}/connection-requests/{request_id}/disclosures",
        response_model=OperatorDisclosuresResponse,
    )
    async def disclosures(
        request: Request,
        response: Response,
        account_id: UUID,
        request_id: UUID,
        query: Annotated[OperatorDisclosuresQuery, Query()],
    ) -> OperatorDisclosuresResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            page = await services.disclosures(
                credential, account_id, request_id, query.filters(), query.cursor
            )
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        if page is None:
            return problem(HTTPStatus.NOT_FOUND, "operator_resource_unavailable")
        private_response(response)
        return disclosures_response(page)

    return router
