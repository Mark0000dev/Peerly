from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, Response
from starlette.responses import JSONResponse

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.browser import BrowserTokenSigner
from studymate.application.report_moderation.history import ReadReportReviewHistory
from studymate.application.report_moderation.review import (
    ReportReviewUnavailableError,
    ReportReviewVersionConflictError,
    ReviewReport,
    ReviewReportCommand,
)
from studymate.domain.report_moderation.reviews import ReportReviewReason
from studymate.presentation.browser import (
    SESSION_AUTH,
    SESSION_COOKIE,
    BrowserConfiguration,
    IdempotentWriteHeaders,
    read_cookie,
    write_credential,
)
from studymate.presentation.operator.router import (
    OPERATOR_ERRORS,
    operator_problem,
    private_response,
)
from studymate.presentation.problems import ProblemResponse, problem
from studymate.presentation.report_moderation.models import (
    ReportReviewHistoryResponse,
    ReportReviewResponse,
    ReviewHistoryQuery,
    ReviewReportBody,
    history_response,
    review_response,
)


@dataclass(frozen=True, slots=True)
class ReportModerationHttpServices:
    review: ReviewReport
    history: ReadReportReviewHistory
    signer: BrowserTokenSigner
    browser: BrowserConfiguration


def report_moderation_router(services: ReportModerationHttpServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/operator/reports",
        tags=["operator"],
        dependencies=[SESSION_AUTH],
        responses={
            code: {"model": ProblemResponse} for code in (401, 403, 404, 409, 413, 415, 422, 503)
        },
    )

    @router.post("/{report_id}/reviews", response_model=ReportReviewResponse)
    async def review(
        report_id: UUID,
        body: ReviewReportBody,
        request: Request,
        response: Response,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> ReportReviewResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            result = await services.review(
                ReviewReportCommand(
                    credential,
                    report_id,
                    body.expected_version,
                    body.action,
                    ReportReviewReason(body.reason),
                    IntentKey(headers.idempotency_key),
                )
            )
        except ReportReviewUnavailableError:
            return problem(HTTPStatus.NOT_FOUND, "operator_resource_unavailable")
        except (ReportReviewVersionConflictError, IdempotencyConflictError) as error:
            return problem(
                HTTPStatus.CONFLICT,
                "idempotency_conflict"
                if isinstance(error, IdempotencyConflictError)
                else "report_review_version_conflict",
            )
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        private_response(response)
        return review_response(result)

    @router.get("/{report_id}/reviews", response_model=ReportReviewHistoryResponse)
    async def history(
        report_id: UUID,
        request: Request,
        response: Response,
        query: Annotated[ReviewHistoryQuery, Query()],
    ) -> ReportReviewHistoryResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.history(credential, report_id, query.cursor)
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        if result is None:
            return problem(HTTPStatus.NOT_FOUND, "operator_resource_unavailable")
        private_response(response)
        return history_response(result)

    return router
