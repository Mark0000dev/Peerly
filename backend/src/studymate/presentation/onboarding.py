from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Header, Request, Response
from starlette.responses import JSONResponse

from studymate.application.idempotency import IntentKey
from studymate.application.identity.browser import BrowserTokenSigner
from studymate.application.profiles.onboarding import ReadOnboardingStatus
from studymate.application.profiles.visibility import (
    ChangeOwnVisibility,
    ChangeVisibilityCommand,
    ProfileRestoreIncompleteError,
    VisibilityVersionConflictError,
)
from studymate.presentation.browser import (
    SESSION_AUTH,
    SESSION_COOKIE,
    BrowserConfiguration,
    IdempotentWriteHeaders,
    read_cookie,
    write_credential,
)
from studymate.presentation.onboarding_models import (
    ChangeVisibilityRequest,
    OnboardingStatusResponse,
    ProfileVisibilityResponse,
    onboarding_response,
    visibility_response,
)
from studymate.presentation.problems import FieldProblem, ProblemResponse, problem
from studymate.presentation.student_errors import STUDENT_ERRORS, student_problem

VISIBILITY_ERRORS = (*STUDENT_ERRORS, ProfileRestoreIncompleteError, VisibilityVersionConflictError)


@dataclass(frozen=True, slots=True)
class OnboardingServices:
    status: ReadOnboardingStatus
    visibility: ChangeOwnVisibility
    signer: BrowserTokenSigner
    browser: BrowserConfiguration


def _error(error: Exception) -> JSONResponse:
    shared = student_problem(error)
    if shared is not None:
        return shared
    if isinstance(error, VisibilityVersionConflictError):
        return problem(
            HTTPStatus.CONFLICT,
            "visibility_version_conflict",
            {"current_version": error.current_version},
        )
    if isinstance(error, ProfileRestoreIncompleteError):
        return problem(
            HTTPStatus.CONFLICT,
            "profile_restore_incomplete",
            errors=tuple(
                FieldProblem(("restore", requirement.value), "required")
                for requirement in error.requirements
            ),
        )
    raise error


def onboarding_router(services: OnboardingServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1",
        tags=["onboarding"],
        dependencies=[SESSION_AUTH],
        responses={
            status.value: {"model": ProblemResponse}
            for status in (
                HTTPStatus.BAD_REQUEST,
                HTTPStatus.UNAUTHORIZED,
                HTTPStatus.FORBIDDEN,
                HTTPStatus.CONFLICT,
                HTTPStatus.REQUEST_TIMEOUT,
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                HTTPStatus.UNPROCESSABLE_ENTITY,
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        },
    )

    @router.get("/me/onboarding", response_model=OnboardingStatusResponse)
    async def status(request: Request, response: Response) -> OnboardingStatusResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            current = await services.status(credential)
        except STUDENT_ERRORS as error:
            return _error(error)
        response.headers["Cache-Control"] = "no-store"
        return onboarding_response(current)

    @router.put("/me/visibility", response_model=ProfileVisibilityResponse)
    async def visibility(
        request: Request,
        body: ChangeVisibilityRequest,
        response: Response,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> ProfileVisibilityResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            current = await services.visibility(
                ChangeVisibilityCommand(
                    credential,
                    body.hidden,
                    body.expected_version,
                    IntentKey(headers.idempotency_key),
                )
            )
        except VISIBILITY_ERRORS as error:
            return _error(error)
        response.headers["Cache-Control"] = "no-store"
        return visibility_response(current)

    return router
