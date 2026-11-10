from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Header, Request, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from studymate.application.errors import StorageUnavailableError
from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.browser import BrowserTokenSigner
from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.application.notification_preferences.preferences import (
    ChooseOwnNotificationPreference,
    ChoosePreferenceCommand,
    PreferenceVersionConflictError,
    ReadOwnNotificationPreference,
)
from studymate.domain.notification_preferences.state import NotificationMode, NotificationPreference
from studymate.presentation.browser import (
    SESSION_AUTH,
    SESSION_COOKIE,
    BrowserConfiguration,
    IdempotentWriteHeaders,
    read_cookie,
    write_credential,
)
from studymate.presentation.problems import ProblemResponse, problem


class PreferenceBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    mode: NotificationMode
    expected_version: int = Field(ge=0, strict=True)


class PreferenceResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    mode: NotificationMode
    version: int = Field(ge=0)
    changed_at: AwareDatetime | None


def preference_response(result: NotificationPreference) -> PreferenceResponse:
    return PreferenceResponse(
        mode=result.mode, version=result.version, changed_at=result.changed_at
    )


@dataclass(frozen=True, slots=True)
class PreferenceHttpServices:
    read: ReadOwnNotificationPreference
    choose: ChooseOwnNotificationPreference
    signer: BrowserTokenSigner
    browser: BrowserConfiguration


PREFERENCE_ERRORS = (
    UnauthenticatedError,
    StudentActionDeniedError,
    IdempotencyConflictError,
    PreferenceVersionConflictError,
    StorageUnavailableError,
)


def preference_problem(error: Exception) -> JSONResponse:
    if isinstance(error, UnauthenticatedError):
        return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
    if isinstance(error, StudentActionDeniedError):
        return problem(HTTPStatus.FORBIDDEN, "student_action_denied")
    if isinstance(error, IdempotencyConflictError):
        return problem(HTTPStatus.CONFLICT, "idempotency_conflict")
    if isinstance(error, PreferenceVersionConflictError):
        return problem(
            HTTPStatus.CONFLICT,
            "notification_preference_version_conflict",
            {"current_version": error.current_version},
        )
    if isinstance(error, StorageUnavailableError):
        result = problem(HTTPStatus.SERVICE_UNAVAILABLE, "storage_unavailable")
        result.headers["Retry-After"] = "1"
        return result
    raise error


def notification_preferences_router(services: PreferenceHttpServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/me",
        tags=["notification-preferences"],
        responses={code: {"model": ProblemResponse} for code in (401, 403, 409, 422, 503)},
    )

    @router.get(
        "/notification-preference", response_model=PreferenceResponse, dependencies=[SESSION_AUTH]
    )
    async def read(request: Request, response: Response) -> PreferenceResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.read(credential)
        except PREFERENCE_ERRORS as error:
            return preference_problem(error)
        response.headers["Cache-Control"] = "no-store"
        return preference_response(result)

    @router.put(
        "/notification-preference", response_model=PreferenceResponse, dependencies=[SESSION_AUTH]
    )
    async def choose(
        request: Request,
        response: Response,
        body: PreferenceBody,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> PreferenceResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            result = await services.choose(
                ChoosePreferenceCommand(
                    credential, body.mode, body.expected_version, IntentKey(headers.idempotency_key)
                )
            )
        except PREFERENCE_ERRORS as error:
            return preference_problem(error)
        response.headers["Cache-Control"] = "no-store"
        return preference_response(result)

    return router
