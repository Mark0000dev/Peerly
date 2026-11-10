from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from studymate.application.errors import StorageUnavailableError
from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.browser import BrowserTokenSigner
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.support.operator import (
    ChangeOperatorSupportStatus,
    ChangeSupportStatusCommand,
    ReadOperatorSupportCase,
    SupportVersionConflictError,
)
from studymate.domain.support.cases import SupportStatus
from studymate.presentation.browser import (
    SESSION_AUTH,
    SESSION_COOKIE,
    BrowserConfiguration,
    IdempotentWriteHeaders,
    read_cookie,
    write_credential,
)
from studymate.presentation.problems import ProblemResponse, problem
from studymate.presentation.support.router import (
    SupportBody,
    SupportReceiptResponse,
    support_problem,
    support_response,
)


class OperatorSupportResponse(SupportBody):
    receipt: SupportReceiptResponse
    actor_id: UUID | None


class SupportStatusBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    status: SupportStatus
    expected_version: int = Field(ge=1, strict=True)


@dataclass(frozen=True, slots=True)
class OperatorSupportHttpServices:
    read: ReadOperatorSupportCase
    change: ChangeOperatorSupportStatus
    signer: BrowserTokenSigner
    browser: BrowserConfiguration


OPERATOR_ERRORS = (
    UnauthenticatedError,
    OperatorAccessDeniedError,
    SupportVersionConflictError,
    IdempotencyConflictError,
    StorageUnavailableError,
)


def _problem(error: Exception) -> JSONResponse:
    if isinstance(error, OperatorAccessDeniedError):
        return problem(HTTPStatus.FORBIDDEN, "operator_access_denied")
    if isinstance(error, SupportVersionConflictError):
        return problem(HTTPStatus.CONFLICT, "support_version_conflict")
    return support_problem(error)


def operator_support_router(services: OperatorSupportHttpServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/operator/cases",
        tags=["operator"],
        dependencies=[SESSION_AUTH],
        responses={code: {"model": ProblemResponse} for code in (401, 403, 404, 409, 422, 503)},
    )

    @router.get("/{case_id}", response_model=OperatorSupportResponse)
    async def read(
        case_id: UUID, request: Request, response: Response
    ) -> OperatorSupportResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.read(credential, case_id)
        except OPERATOR_ERRORS as error:
            return _problem(error)
        if result is None:
            return problem(HTTPStatus.NOT_FOUND, "support_unavailable")
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return OperatorSupportResponse(
            topic=result.content.topic,
            reply_address=result.content.reply_address,
            message=result.content.message,
            details=result.content.details,
            receipt=support_response(result.receipt),
            actor_id=result.actor_id,
        )

    @router.put("/{case_id}/status", response_model=SupportReceiptResponse)
    async def change(
        case_id: UUID,
        request: Request,
        response: Response,
        body: SupportStatusBody,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> SupportReceiptResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            result = await services.change(
                ChangeSupportStatusCommand(
                    credential,
                    case_id,
                    body.status,
                    body.expected_version,
                    IntentKey(headers.idempotency_key),
                )
            )
        except OPERATOR_ERRORS as error:
            return _problem(error)
        if result is None:
            return problem(HTTPStatus.NOT_FOUND, "support_unavailable")
        response.headers["Cache-Control"] = "no-store"
        return support_response(result)

    return router
