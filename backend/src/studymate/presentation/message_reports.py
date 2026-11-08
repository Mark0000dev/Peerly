"""Explicit report evidence under current accepted-participant authority."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response
from starlette.responses import JSONResponse

from studymate.application.identity.browser import BrowserTokenSigner
from studymate.application.messaging.ports import ConversationUnavailableError
from studymate.application.safety.message_reports import IssueMessageImageReportContext
from studymate.application.safety.profile_reports import ReportContextUnavailableError
from studymate.presentation.browser import (
    SESSION_AUTH,
    BrowserConfiguration,
    BrowserWriteHeaders,
    write_credential,
)
from studymate.presentation.people_models import (
    MessageImageReportContextResponse,
    message_report_context,
)
from studymate.presentation.problems import ProblemResponse, problem
from studymate.presentation.student_errors import STUDENT_ERRORS, student_problem


@dataclass(frozen=True, slots=True)
class MessageReportContextServices:
    issue: IssueMessageImageReportContext
    signer: BrowserTokenSigner
    browser: BrowserConfiguration


def message_report_context_router(services: MessageReportContextServices) -> APIRouter:
    router = APIRouter(
        prefix="/conversations",
        tags=["safety"],
        dependencies=[SESSION_AUTH],
        responses={
            status.value: {"model": ProblemResponse}
            for status in (
                HTTPStatus.BAD_REQUEST,
                HTTPStatus.UNAUTHORIZED,
                HTTPStatus.FORBIDDEN,
                HTTPStatus.NOT_FOUND,
                HTTPStatus.CONFLICT,
                HTTPStatus.REQUEST_TIMEOUT,
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                HTTPStatus.UNPROCESSABLE_ENTITY,
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        },
    )

    @router.post(
        "/{conversation_id}/messages/{message_id}/report-contexts",
        response_model=MessageImageReportContextResponse,
        status_code=HTTPStatus.CREATED,
    )
    async def issue_context(
        request: Request,
        response: Response,
        conversation_id: UUID,
        message_id: UUID,
        headers: Annotated[BrowserWriteHeaders, Header()],
    ) -> MessageImageReportContextResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            result = await services.issue(credential, conversation_id, message_id)
        except (
            *STUDENT_ERRORS,
            ConversationUnavailableError,
            ReportContextUnavailableError,
        ) as error:
            shared = student_problem(error)
            if shared is not None:
                return shared
            return problem(HTTPStatus.NOT_FOUND, "report_context_unavailable")
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return message_report_context(result)

    return router
