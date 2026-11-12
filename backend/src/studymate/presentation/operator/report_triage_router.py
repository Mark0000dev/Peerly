from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response
from starlette.responses import JSONResponse

from studymate.application.ai.ports import (
    AiQuotaError,
    AiSourceUnavailableError,
    AiUnavailableError,
)
from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.browser import BrowserTokenSigner
from studymate.application.operator.report_triage import (
    EnqueueReportTriage,
    EnqueueReportTriageCommand,
    ReadReportTriage,
    ReadReportTriageContext,
)
from studymate.application.operator.report_triage_ports import (
    InvalidReportTriageSourceError,
    ReportTriageSourceUnavailableError,
)
from studymate.presentation.browser import (
    SESSION_AUTH,
    SESSION_COOKIE,
    BrowserConfiguration,
    IdempotentWriteHeaders,
    read_cookie,
    write_credential,
)
from studymate.presentation.operator.report_triage_models import (
    ReportTriageBody,
    ReportTriageContextResponse,
    ReportTriageReadResponse,
    ReportTriageResponse,
    report_triage_read_response,
    report_triage_response,
    triage_context_response,
)
from studymate.presentation.operator.router import (
    OPERATOR_ERRORS,
    operator_problem,
    private_response,
)
from studymate.presentation.problems import ProblemResponse, problem

TRIAGE_ERRORS = (
    *OPERATOR_ERRORS,
    AiQuotaError,
    AiSourceUnavailableError,
    AiUnavailableError,
    IdempotencyConflictError,
    InvalidReportTriageSourceError,
    ReportTriageSourceUnavailableError,
)


def triage_problem(error: Exception) -> JSONResponse:
    if isinstance(error, AiUnavailableError):
        response = problem(HTTPStatus.SERVICE_UNAVAILABLE, "ai_unavailable")
        response.headers["Retry-After"] = "1"
        return response
    if isinstance(error, AiQuotaError):
        response = problem(HTTPStatus.TOO_MANY_REQUESTS, "ai_quota_exceeded")
        response.headers["Retry-After"] = "1"
        return response
    if isinstance(error, IdempotencyConflictError):
        return problem(HTTPStatus.CONFLICT, "idempotency_conflict")
    if isinstance(
        error,
        (
            InvalidReportTriageSourceError,
            ReportTriageSourceUnavailableError,
            AiSourceUnavailableError,
        ),
    ):
        return problem(HTTPStatus.CONFLICT, "report_triage_source_unavailable")
    return operator_problem(error)


@dataclass(frozen=True, slots=True)
class OperatorReportTriageHttpServices:
    context: ReadReportTriageContext
    enqueue: EnqueueReportTriage
    read: ReadReportTriage
    signer: BrowserTokenSigner
    browser: BrowserConfiguration


def operator_report_triage_router(services: OperatorReportTriageHttpServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/operator/reports",
        tags=["operator"],
        dependencies=[SESSION_AUTH],
        responses={
            code: {"model": ProblemResponse}
            for code in (401, 403, 404, 409, 413, 415, 422, 429, 503)
        },
    )

    @router.get("/{report_id}/triage-source", response_model=ReportTriageContextResponse)
    async def context(
        report_id: UUID, request: Request, response: Response
    ) -> ReportTriageContextResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            value = await services.context(credential, report_id)
        except TRIAGE_ERRORS as error:
            return triage_problem(error)
        if value is None:
            return problem(HTTPStatus.NOT_FOUND, "operator_resource_unavailable")
        private_response(response)
        return triage_context_response(value)

    @router.post("/{report_id}/triage", response_model=ReportTriageResponse)
    async def enqueue(
        report_id: UUID,
        body: ReportTriageBody,
        request: Request,
        response: Response,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> ReportTriageResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            value = await services.enqueue(
                EnqueueReportTriageCommand(
                    credential, report_id, body.source_token, IntentKey(headers.idempotency_key)
                )
            )
        except TRIAGE_ERRORS as error:
            return triage_problem(error)
        private_response(response)
        return report_triage_response(value)

    @router.get("/{report_id}/triage", response_model=ReportTriageReadResponse)
    async def read(
        report_id: UUID, request: Request, response: Response
    ) -> ReportTriageReadResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            value = await services.read(credential, report_id)
        except TRIAGE_ERRORS as error:
            return triage_problem(error)
        if value is None:
            return problem(HTTPStatus.NOT_FOUND, "operator_resource_unavailable")
        private_response(response)
        return report_triage_read_response(value)

    return router
