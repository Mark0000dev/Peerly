"""Retained report read factory, locally mounted by main; provisioning stays main-owned."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from studymate.application.operator.profile_reports import (
    ReadOperatorProfileReport,
    SearchOperatorProfileReports,
)
from studymate.presentation.browser import SESSION_AUTH, SESSION_COOKIE, read_cookie
from studymate.presentation.operator.report_models import (
    OperatorReportDetailResponse,
    OperatorReportQuery,
    OperatorReportsResponse,
    report_detail_response,
    reports_response,
)
from studymate.presentation.operator.router import (
    OPERATOR_ERRORS,
    operator_problem,
    private_response,
)
from studymate.presentation.problems import ProblemResponse, problem


@dataclass(frozen=True, slots=True)
class OperatorReportHttpServices:
    search: SearchOperatorProfileReports
    report: ReadOperatorProfileReport


def operator_report_router(services: OperatorReportHttpServices) -> APIRouter:
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

    @router.get("/reports", response_model=OperatorReportsResponse)
    async def search(
        request: Request, response: Response, query: Annotated[OperatorReportQuery, Query()]
    ) -> OperatorReportsResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.search(credential, query.filters(), query.cursor)
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        private_response(response)
        return reports_response(result)

    @router.get("/reports/{report_id}", response_model=OperatorReportDetailResponse)
    async def report(
        request: Request, response: Response, report_id: UUID
    ) -> OperatorReportDetailResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.report(credential, report_id)
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        if result is None:
            return problem(HTTPStatus.NOT_FOUND, "operator_resource_unavailable")
        private_response(response)
        return report_detail_response(result)

    return router
