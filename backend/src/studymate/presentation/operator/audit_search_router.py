"""Unmounted audit list, independent of existing GET/audits/{id} detail."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from studymate.application.operator.audit_search import SearchOperatorAudits
from studymate.presentation.browser import SESSION_AUTH, SESSION_COOKIE, read_cookie
from studymate.presentation.operator.audit_search_models import (
    OperatorAuditQuery,
    OperatorAuditsResponse,
    audits_response,
)
from studymate.presentation.operator.router import (
    OPERATOR_ERRORS,
    operator_problem,
    private_response,
)
from studymate.presentation.problems import ProblemResponse, problem


@dataclass(frozen=True, slots=True)
class OperatorAuditSearchHttpServices:
    search: SearchOperatorAudits


def operator_audit_search_router(services: OperatorAuditSearchHttpServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/operator",
        tags=["operator"],
        dependencies=[SESSION_AUTH],
        responses={code: {"model": ProblemResponse} for code in (401, 403, 422, 503)},
    )

    @router.get("/audits", response_model=OperatorAuditsResponse)
    async def search(
        request: Request, response: Response, query: Annotated[OperatorAuditQuery, Query()]
    ) -> OperatorAuditsResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.search(credential, query.filters(), query.cursor)
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        private_response(response)
        return audits_response(result)

    return router
