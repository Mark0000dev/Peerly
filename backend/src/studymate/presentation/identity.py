from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from ipaddress import ip_address
from math import ceil
from typing import Annotated, Literal
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse, RedirectResponse, Response

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.bootstrap import ReadBootstrap
from studymate.application.identity.browser import BrowserTokenSigner
from studymate.application.identity.email_verification import (
    EmailActionDeniedError,
    EmailChallengeUnavailableError,
    EmailDeliveryState,
    EmailRateLimitedError,
    ReadChallengeCommand,
    ReadEmailChallenge,
    StartChallengeCommand,
    StartEmailChallenge,
    VerificationCode,
    VerificationOutcome,
    VerifyChallengeCommand,
    VerifyStudentEmail,
)
from studymate.application.identity.google import (
    GoogleRejectedError,
    GoogleUnavailableError,
)
from studymate.application.identity.login import (
    AccountUnavailableError,
    BeginGoogleLogin,
    CallbackRateLimitedError,
    GoogleCallbackCommand,
    HandleGoogleCallback,
    LoginCancelledError,
    LoginRateLimitedError,
)
from studymate.application.identity.sessions import Logout, UnauthenticatedError
from studymate.domain.identity import StudentEmail
from studymate.domain.membership import ChallengeState
from studymate.presentation.browser import (
    SESSION_AUTH,
    SESSION_COOKIE,
    BrowserConfiguration,
    BrowserWriteHeaders,
    IdempotentWriteHeaders,
    clear_session_cookie,
    read_cookie,
    write_credential,
)
from studymate.presentation.problems import ProblemResponse, problem
from studymate.presentation.registration_models import RegistrationReceiptResponse, receipt_response

LOGIN_COOKIE = "__Host-studymate_login"
COOKIE_LIFETIME = 604800
LOGIN_COOKIE_LIFETIME = 300
STATE_LENGTH = 43
API_PREFIX = "/api/v1"


@dataclass(frozen=True, slots=True)
class AuthenticationServices:
    begin: BeginGoogleLogin
    complete: HandleGoogleCallback
    bootstrap: ReadBootstrap
    logout: Logout
    signer: BrowserTokenSigner
    browser: BrowserConfiguration
    start_email: StartEmailChallenge
    verify_email: VerifyStudentEmail
    read_email: ReadEmailChallenge


class CapabilitiesResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    can_verify_student_email: bool
    can_begin_onboarding: bool
    can_use_student_features: bool


class IdentityResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    account_id: UUID
    account_status: Literal["active", "banned"]
    membership_status: Literal["unverified", "verified", "revoked"]
    verified_at: datetime | None
    registration: RegistrationReceiptResponse | None
    email_challenge_id: UUID | None
    capabilities: CapabilitiesResponse
    csrf_token: str


def _clear_cookie(response: Response, name: str) -> None:
    response.delete_cookie(name, path="/", secure=True, httponly=True, samesite="lax")


def _callback_limited(error: CallbackRateLimitedError) -> JSONResponse:
    response = problem(
        HTTPStatus.TOO_MANY_REQUESTS,
        "login_rate_limited",
        {"retry_at": error.retry_at.isoformat()},
    )
    response.headers["Retry-After"] = str(
        max(1, ceil((error.retry_at - datetime.now(UTC)).total_seconds()))
    )
    return response


def _browser_callback_failure(request: Request, response: Response, origin: str) -> Response:
    # Navigation opts in explicitly; API clients keep their problem status/body.
    accepts_html = any(
        item.split(";", 1)[0].strip().lower() == "text/html"
        for item in request.headers.get("accept", "").split(",")
    )
    if not accepts_html or not isinstance(response, JSONResponse):
        return response
    payload = ProblemResponse.model_validate_json(bytes(response.body))
    query = urlencode({"auth_error": payload.code, "auth_ref": payload.request_id})
    redirect = RedirectResponse(origin + "/onboarding?" + query, status_code=HTTPStatus.SEE_OTHER)
    redirect.headers["Cache-Control"] = "no-store"
    redirect.headers["Referrer-Policy"] = "no-referrer"
    redirect.headers["X-Auth-Error-Status"] = str(response.status_code)
    if "Retry-After" in response.headers:
        redirect.headers["Retry-After"] = response.headers["Retry-After"]
    return redirect


def _google_start_router(services: AuthenticationServices) -> APIRouter:
    router = APIRouter(prefix=API_PREFIX)

    @router.get("/auth/google/start", response_model=None, status_code=HTTPStatus.SEE_OTHER)
    async def google_start(request: Request) -> Response:
        response: Response
        if request.client is None:
            return problem(HTTPStatus.BAD_REQUEST, "request_context_invalid")
        try:
            address = str(ip_address(request.client.host))
        except ValueError:
            return problem(HTTPStatus.BAD_REQUEST, "request_context_invalid")
        try:
            started = await services.begin(
                return_to=request.query_params.get("return_to", "/onboarding"),
                source_digest=await services.signer.source_digest(address),
                previous_browser=read_cookie(request, LOGIN_COOKIE),
            )
        except GoogleRejectedError:
            return problem(HTTPStatus.BAD_REQUEST, "login_return_route_invalid")
        except LoginRateLimitedError:
            response = problem(HTTPStatus.TOO_MANY_REQUESTS, "login_rate_limited")
            response.headers["Retry-After"] = "3600"
            return response
        response = RedirectResponse(started.redirect_url, status_code=HTTPStatus.SEE_OTHER)
        response.set_cookie(
            LOGIN_COOKIE,
            started.browser.value,
            max_age=LOGIN_COOKIE_LIFETIME,
            secure=True,
            httponly=True,
            samesite="lax",
            path="/",
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    return router


def _google_router(services: AuthenticationServices) -> APIRouter:
    router = APIRouter()
    router.include_router(_google_start_router(services))

    @router.get(
        API_PREFIX + "/auth/google/callback",
        response_model=None,
        status_code=HTTPStatus.SEE_OTHER,
        description=(
            "Browser navigation (Accept: text/html) redirects expected failures to the fixed "
            "/onboarding route with auth_error and nonsecret auth_ref (server request UUID). "
            "Codes: login_invalid, login_cancelled, login_provider_unavailable, "
            "login_rate_limited, account_unavailable, request_context_invalid. "
            "X-Auth-Error-Status preserves the original problem status; Retry-After is retained. "
            "Other clients retain problem JSON/status. Unexpected server failures remain errors."
        ),
    )
    async def google_callback(request: Request) -> Response:
        response: Response
        browser = read_cookie(request, LOGIN_COOKIE)
        state = request.query_params.get("state", "")
        code = request.query_params.get("code")
        error = request.query_params.get("error")
        malformed = (
            browser is None
            or len(state) != STATE_LENGTH
            or len(request.query_params.getlist("state")) != 1
            or len(request.query_params.getlist("code")) > 1
            or len(request.query_params.getlist("error")) > 1
            or (code is None) == (error is None)
        )
        if request.client is None:
            response = problem(HTTPStatus.BAD_REQUEST, "request_context_invalid")
        else:
            try:
                source = await services.signer.source_digest(str(ip_address(request.client.host)))
            except ValueError:
                response = problem(HTTPStatus.BAD_REQUEST, "request_context_invalid")
                response = _browser_callback_failure(
                    request, response, services.browser.public_origin
                )
                _clear_cookie(response, LOGIN_COOKIE)
                return response
            try:
                completed = await services.complete(
                    GoogleCallbackCommand(
                        source_digest=source,
                        state=state,
                        browser=browser,
                        code=code,
                        malformed=malformed,
                        cancelled=error == "access_denied",
                        previous=read_cookie(request, SESSION_COOKIE),
                    )
                )
            except CallbackRateLimitedError as limited:
                response = _callback_limited(limited)
            except AccountUnavailableError:
                response = problem(HTTPStatus.FORBIDDEN, "account_unavailable")
            except LoginCancelledError:
                response = problem(HTTPStatus.BAD_REQUEST, "login_cancelled")
            except GoogleRejectedError:
                response = problem(HTTPStatus.BAD_REQUEST, "login_invalid")
            except GoogleUnavailableError:
                response = problem(HTTPStatus.SERVICE_UNAVAILABLE, "login_provider_unavailable")
            else:
                response = RedirectResponse(
                    services.browser.public_origin + completed.return_to,
                    status_code=HTTPStatus.SEE_OTHER,
                )
                response.set_cookie(
                    SESSION_COOKIE,
                    completed.credential.value,
                    max_age=COOKIE_LIFETIME,
                    secure=True,
                    httponly=True,
                    samesite="lax",
                    path="/",
                )
                response.headers["Cache-Control"] = "no-store"
                response.headers["Referrer-Policy"] = "no-referrer"
        response = _browser_callback_failure(request, response, services.browser.public_origin)
        _clear_cookie(response, LOGIN_COOKIE)
        return response

    return router


def _session_router(services: AuthenticationServices) -> APIRouter:
    router = APIRouter(prefix=API_PREFIX, dependencies=[SESSION_AUTH])

    @router.get("/me", response_model=IdentityResponse)
    async def me(request: Request, response: Response) -> IdentityResponse | Response:
        response.headers["Cache-Control"] = "no-store"
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            identity = await services.bootstrap(credential)
        except UnauthenticatedError:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        return IdentityResponse(
            account_id=identity.account_id,
            account_status=identity.account_status,
            membership_status=identity.membership_status,
            verified_at=identity.verified_at,
            email_challenge_id=identity.email_challenge_id,
            registration=receipt_response(identity.registration)
            if identity.registration is not None
            else None,
            capabilities=CapabilitiesResponse(
                can_verify_student_email=identity.capabilities.can_verify_student_email,
                can_begin_onboarding=identity.capabilities.can_begin_onboarding,
                can_use_student_features=identity.capabilities.can_use_student_features,
            ),
            csrf_token=await services.signer.csrf_token(credential),
        )

    @router.post("/auth/logout", status_code=HTTPStatus.NO_CONTENT, response_class=Response)
    async def logout(
        request: Request, headers: Annotated[BrowserWriteHeaders, Header()]
    ) -> Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if headers.origin not in services.browser.trusted_origins:
            return problem(HTTPStatus.FORBIDDEN, "origin_denied")
        if credential is not None:
            if not await services.signer.valid_csrf(credential, headers.x_csrf_token or ""):
                return problem(HTTPStatus.FORBIDDEN, "csrf_denied")
            await services.logout(credential)
        response = Response(
            status_code=HTTPStatus.NO_CONTENT, headers={"Cache-Control": "no-store"}
        )
        clear_session_cookie(response)
        return response

    return router


def identity_router(services: AuthenticationServices) -> APIRouter:
    router = APIRouter(
        tags=["identity"],
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
                HTTPStatus.TOO_MANY_REQUESTS,
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        },
    )
    router.include_router(_google_router(services))
    router.include_router(_session_router(services))
    router.include_router(_email_router(services))
    return router


class StartEmailRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    email: str = Field(min_length=1, max_length=254)
    resend_of: UUID | None = None


class VerifyEmailRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    code: str = Field(pattern=r"^[0-9]{6}$")


class ChallengeResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID
    expires_at: datetime
    resend_at: datetime


class ChallengeStatusResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID
    email: str = Field(repr=False)
    state: ChallengeState
    delivery: EmailDeliveryState = Field(
        description="sent means SMTP/provider acceptance, not proof of inbox delivery"
    )
    verification_outcome: VerificationOutcome | None
    expires_at: datetime
    resend_at: datetime
    attempts_remaining: int
    can_verify: bool
    can_resend: bool


class VerificationResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    verified_at: datetime


def _email_error(error: Exception) -> JSONResponse:
    if isinstance(error, UnauthenticatedError):
        return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
    if isinstance(error, EmailActionDeniedError):
        return problem(HTTPStatus.FORBIDDEN, "verification_not_allowed")
    if isinstance(error, EmailChallengeUnavailableError):
        return problem(HTTPStatus.NOT_FOUND, "challenge_unavailable")
    if isinstance(error, IdempotencyConflictError):
        return problem(HTTPStatus.CONFLICT, "idempotency_conflict")
    if isinstance(error, EmailRateLimitedError):
        response = problem(
            HTTPStatus.TOO_MANY_REQUESTS,
            "verification_rate_limited",
            {"retry_at": error.retry_at.isoformat()},
        )
        response.headers["Retry-After"] = str(
            max(1, ceil((error.retry_at - datetime.now(UTC)).total_seconds()))
        )
        return response
    raise error


def _email_router(services: AuthenticationServices) -> APIRouter:
    router = APIRouter(prefix=API_PREFIX, dependencies=[SESSION_AUTH])

    @router.get("/auth/email-challenges/{challenge_id}", response_model=ChallengeStatusResponse)
    async def challenge_status(
        request: Request, challenge_id: UUID, response: Response
    ) -> ChallengeStatusResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        if request.client is None:
            return problem(HTTPStatus.BAD_REQUEST, "request_context_invalid")
        try:
            source = await services.signer.source_digest(str(ip_address(request.client.host)))
        except ValueError:
            return problem(HTTPStatus.BAD_REQUEST, "request_context_invalid")
        try:
            status = await services.read_email(
                ReadChallengeCommand(credential, challenge_id, source)
            )
        except (
            UnauthenticatedError,
            EmailActionDeniedError,
            EmailChallengeUnavailableError,
        ) as error:
            return _email_error(error)
        response.headers["Cache-Control"] = "no-store"
        return ChallengeStatusResponse(
            id=status.id,
            email=status.email.value,
            state=status.state,
            delivery=status.delivery,
            verification_outcome=status.verification_outcome,
            expires_at=status.expires_at,
            resend_at=status.resend_at,
            attempts_remaining=status.attempts_remaining,
            can_verify=status.can_verify,
            can_resend=status.can_resend,
        )

    @router.post(
        "/auth/email-challenges", status_code=HTTPStatus.ACCEPTED, response_model=ChallengeResponse
    )
    async def start_email(
        request: Request,
        body: StartEmailRequest,
        response: Response,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> ChallengeResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            if request.client is None:
                return problem(HTTPStatus.BAD_REQUEST, "request_context_invalid")
            command = StartChallengeCommand(
                credential=credential,
                email=StudentEmail(body.email),
                intent_key=IntentKey(headers.idempotency_key),
                source_digest=await services.signer.source_digest(
                    str(ip_address(request.client.host))
                ),
                resend_of=body.resend_of,
            )
        except ValueError:
            return problem(HTTPStatus.UNPROCESSABLE_ENTITY, "verification_input_invalid")
        try:
            created = await services.start_email(command)
        except (
            UnauthenticatedError,
            EmailActionDeniedError,
            EmailChallengeUnavailableError,
            IdempotencyConflictError,
            EmailRateLimitedError,
        ) as error:
            return _email_error(error)
        response.headers["Cache-Control"] = "no-store"
        return ChallengeResponse(
            id=created.id, expires_at=created.expires_at, resend_at=created.resend_at
        )

    @router.post(
        "/auth/email-challenges/{challenge_id}/verify", response_model=VerificationResponse
    )
    async def verify_email(
        request: Request,
        challenge_id: UUID,
        body: VerifyEmailRequest,
        response: Response,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> VerificationResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            command = VerifyChallengeCommand(
                credential,
                challenge_id,
                VerificationCode(body.code),
                IntentKey(headers.idempotency_key),
            )
        except ValueError:
            return problem(HTTPStatus.UNPROCESSABLE_ENTITY, "verification_input_invalid")
        try:
            result = await services.verify_email(command)
        except (
            UnauthenticatedError,
            EmailActionDeniedError,
            EmailChallengeUnavailableError,
            IdempotencyConflictError,
            EmailRateLimitedError,
        ) as error:
            return _email_error(error)
        if result.outcome != VerificationOutcome.VERIFIED:
            status = (
                HTTPStatus.CONFLICT
                if result.outcome
                in (VerificationOutcome.SUPPORT_REQUIRED, VerificationOutcome.UNAVAILABLE)
                else HTTPStatus.UNPROCESSABLE_ENTITY
            )
            return problem(
                status,
                "verification_" + result.outcome.value,
                {"attempts_remaining": result.attempts_remaining},
            )
        if result.verified_at is None:
            raise RuntimeError("Successful verification lacks a timestamp")
        response.headers["Cache-Control"] = "no-store"
        return VerificationResponse(verified_at=result.verified_at)

    return router
