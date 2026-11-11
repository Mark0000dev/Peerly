"""Mounted at actual72/head43; no queue/executor/provider authority."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from studymate.application.operator.ai_jobs import ReadOperatorAiJob, ReadOperatorAiJobs
from studymate.presentation.browser import SESSION_AUTH, SESSION_COOKIE, read_cookie
from studymate.presentation.operator.ai_models import (
    OperatorAiJobQuery,
    OperatorAiJobResponse,
    OperatorAiJobsQuery,
    OperatorAiJobsResponse,
    ai_job_response,
    ai_jobs_response,
)
from studymate.presentation.operator.router import (
    OPERATOR_ERRORS,
    operator_problem,
    private_response,
)
from studymate.presentation.problems import ProblemResponse, problem


@dataclass(frozen=True, slots=True)
class OperatorAiHttpServices:
    jobs: ReadOperatorAiJobs
    job: ReadOperatorAiJob


def operator_ai_router(services: OperatorAiHttpServices) -> APIRouter:
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

    @router.get("/accounts/{account_id}/ai-jobs", response_model=OperatorAiJobsResponse)
    async def jobs(
        request: Request,
        response: Response,
        account_id: UUID,
        query: Annotated[OperatorAiJobsQuery, Query()],
    ) -> OperatorAiJobsResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.jobs(credential, account_id, query.filters(), query.cursor)
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        if result is None:
            return problem(HTTPStatus.NOT_FOUND, "operator_resource_unavailable")
        private_response(response)
        return ai_jobs_response(result)

    @router.get("/accounts/{account_id}/ai-jobs/{job_id}", response_model=OperatorAiJobResponse)
    async def job(
        request: Request,
        response: Response,
        account_id: UUID,
        job_id: UUID,
        _query: Annotated[OperatorAiJobQuery, Query()],
    ) -> OperatorAiJobResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.job(credential, account_id, job_id)
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        if result is None:
            return problem(HTTPStatus.NOT_FOUND, "operator_resource_unavailable")
        private_response(response)
        return ai_job_response(result)

    return router
