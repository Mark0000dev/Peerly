from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response
from starlette.responses import JSONResponse

from studymate.application.ai.ports import (
    AiJobNotFoundError,
    AiQuotaError,
    AiSourceUnavailableError,
    AiUnavailableError,
)
from studymate.application.ai.student import CancelStudentJob, ReadStudentJob, SubmitStudentJob
from studymate.application.errors import StorageUnavailableError
from studymate.application.idempotency import IntentKey
from studymate.application.identity.browser import BrowserTokenSigner
from studymate.presentation.ai.models import CreateJobRequest, JobResponse, job_response
from studymate.presentation.browser import (
    SESSION_AUTH,
    SESSION_COOKIE,
    BrowserConfiguration,
    BrowserWriteHeaders,
    IdempotentWriteHeaders,
    read_cookie,
    write_credential,
)
from studymate.presentation.problems import ProblemResponse, problem
from studymate.presentation.student_errors import STUDENT_ERRORS, student_problem

AI_ERRORS = (
    *STUDENT_ERRORS,
    AiJobNotFoundError,
    AiQuotaError,
    AiSourceUnavailableError,
    AiUnavailableError,
    StorageUnavailableError,
)
MAX_RETRY_AFTER_SECONDS = 60


@dataclass(frozen=True, slots=True)
class AiHttpServices:
    submit: SubmitStudentJob
    read: ReadStudentJob
    cancel: CancelStudentJob
    signer: BrowserTokenSigner
    browser: BrowserConfiguration
    accepting: bool = False
    retry_after_seconds: int = 1

    def __post_init__(self) -> None:
        if not 1 <= self.retry_after_seconds <= MAX_RETRY_AFTER_SECONDS:
            raise ValueError("AI HTTP retry backoff must be positive and bounded")


def _unavailable(services: AiHttpServices) -> JSONResponse:
    response = problem(HTTPStatus.SERVICE_UNAVAILABLE, "ai_unavailable")
    response.headers["Retry-After"] = str(services.retry_after_seconds)
    return response


def _error(error: Exception, services: AiHttpServices) -> JSONResponse:
    common = student_problem(error)
    if common is not None:
        return common
    if isinstance(error, AiJobNotFoundError):
        return problem(HTTPStatus.NOT_FOUND, "ai_job_unavailable")
    if isinstance(error, AiSourceUnavailableError):
        return problem(HTTPStatus.CONFLICT, "ai_source_unavailable")
    if isinstance(error, AiQuotaError):
        response = problem(HTTPStatus.TOO_MANY_REQUESTS, "ai_quota_exceeded")
        response.headers["Retry-After"] = str(services.retry_after_seconds)
        return response
    if isinstance(error, (AiUnavailableError, StorageUnavailableError)):
        return _unavailable(services)
    raise error


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"


def ai_router(services: AiHttpServices) -> APIRouter:
    """Factory only; owner installs shared JSON body/error/correlation middleware.

    Accepting is explicit and defaults OFF. It is not inferred from credentials,
    a fake executor or database availability. Read/cancel remain available.
    """
    router = APIRouter(
        prefix="/api/v1/ai/jobs",
        tags=["ai"],
        dependencies=[SESSION_AUTH],
        responses={
            status.value: {"model": ProblemResponse}
            for status in (
                HTTPStatus.BAD_REQUEST,
                HTTPStatus.UNAUTHORIZED,
                HTTPStatus.FORBIDDEN,
                HTTPStatus.NOT_FOUND,
                HTTPStatus.CONFLICT,
                HTTPStatus.UNPROCESSABLE_ENTITY,
                HTTPStatus.REQUEST_TIMEOUT,
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                HTTPStatus.TOO_MANY_REQUESTS,
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        },
    )

    @router.post("", status_code=HTTPStatus.ACCEPTED, response_model=JobResponse)
    async def create(
        request: Request,
        body: CreateJobRequest,
        response: Response,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> JobResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            saved = await services.submit(
                credential,
                body.submission(),
                IntentKey(headers.idempotency_key),
                accepting=services.accepting,
            )
            result = job_response(saved)
        except AI_ERRORS as error:
            return _error(error, services)
        _private(response)
        response.headers["Location"] = f"/api/v1/ai/jobs/{saved.id}"
        return result

    @router.get("/{job_id}", response_model=JobResponse)
    async def read(request: Request, job_id: UUID, response: Response) -> JobResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = job_response(await services.read(credential, job_id))
        except AI_ERRORS as error:
            return _error(error, services)
        _private(response)
        return result

    @router.post("/{job_id}/cancel", response_model=JobResponse)
    async def cancel(
        request: Request,
        job_id: UUID,
        response: Response,
        headers: Annotated[BrowserWriteHeaders, Header()],
    ) -> JobResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            result = job_response(await services.cancel(credential, job_id))
        except AI_ERRORS as error:
            return _error(error, services)
        _private(response)
        return result

    return router
