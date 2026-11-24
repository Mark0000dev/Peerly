"""Native authentication endpoints. Session material leaves only in Set-Cookie."""

from dataclasses import dataclass
from http import HTTPStatus
from ipaddress import ip_address
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import HTMLResponse, RedirectResponse, Response

from studymate.application.identity.browser import BrowserTokenSigner
from studymate.application.identity.google import GoogleRejectedError
from studymate.application.identity.login import LoginRateLimitedError
from studymate.application.identity.native_login import (
    BeginNativeLogin,
    ExchangeNativeAttempt,
    NativeLoginPendingError,
    NativeLoginRejectedError,
)
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.presentation.browser import (
    SESSION_COOKIE,
    BrowserConfiguration,
    BrowserWriteHeaders,
    read_cookie,
)
from studymate.presentation.identity import (
    COOKIE_LIFETIME,
    LOGIN_COOKIE,
    LOGIN_COOKIE_LIFETIME,
    NATIVE_LOGIN_COOKIE,
)
from studymate.presentation.problems import ProblemResponse, problem


@dataclass(frozen=True, slots=True)
class NativeServices:
    signer: BrowserTokenSigner
    start: BeginNativeLogin
    exchange: ExchangeNativeAttempt
    browser: BrowserConfiguration
    # Fixed owner-reviewed custom-scheme wake URL. No request-controlled return target.
    wake_url: str

    def __post_init__(self) -> None:
        # Only the two owner-approved application wake routes are accepted.
        if self.wake_url not in {
            "dev.alekseiorlov.peerly://auth/complete",
            "dev.alekseiorlov.peerly.staging://auth/complete",
        }:
            raise ValueError("Native wake route requires explicit reviewed configuration")

    def finish(self) -> Response:
        # Clear the Google callback query from the browser's committed page URL.
        response = RedirectResponse(
            self.browser.public_origin + "/api/v1/auth/native/return",
            status_code=HTTPStatus.SEE_OTHER,
        )
        response.delete_cookie(LOGIN_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
        response.delete_cookie(
            NATIVE_LOGIN_COOKIE, path="/", secure=True, httponly=True, samesite="lax"
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def return_page(self) -> Response:
        # An explicit user gesture is reliable when the browser blocks automatic
        # custom-scheme redirects. Same fixed page for success/failure, no identity.
        response = HTMLResponse(
            '<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            "<title>Return to Peerly</title><main><h1>Return to Peerly</h1>"
            "<p>Continue sign-in in the Peerly app.</p>"
            f'<a href="{self.wake_url}">Return to Peerly</a></main></html>'
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
        )
        return response


class NativeExchangeRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    attempt_id: UUID
    verifier: str = Field(min_length=43, max_length=128, repr=False)


def native_router(services: NativeServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/auth/native",
        tags=["identity"],
        responses={
            status.value: {"model": ProblemResponse}
            for status in (
                HTTPStatus.BAD_REQUEST,
                HTTPStatus.FORBIDDEN,
                HTTPStatus.CONFLICT,
                HTTPStatus.UNPROCESSABLE_ENTITY,
                HTTPStatus.TOO_MANY_REQUESTS,
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        },
    )

    @router.get("/return", response_model=None)
    async def return_page() -> Response:
        return services.return_page()

    @router.get("/start", response_model=None)
    async def start(request: Request, attempt_id: UUID, challenge: str) -> Response:
        if request.client is None or any(
            len(request.query_params.getlist(key)) != 1 for key in ("attempt_id", "challenge")
        ):
            return problem(HTTPStatus.BAD_REQUEST, "native_login_invalid")
        try:
            source = await services.signer.source_digest(str(ip_address(request.client.host)))
            started = await services.start(
                attempt_id, challenge, source, read_cookie(request, LOGIN_COOKIE)
            )
        except (ValueError, GoogleRejectedError, NativeLoginRejectedError):
            return problem(HTTPStatus.BAD_REQUEST, "native_login_invalid")
        except LoginRateLimitedError:
            return problem(HTTPStatus.TOO_MANY_REQUESTS, "login_rate_limited")
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
        response.set_cookie(
            NATIVE_LOGIN_COOKIE,
            "1",
            max_age=LOGIN_COOKIE_LIFETIME,
            secure=True,
            httponly=True,
            samesite="lax",
            path="/",
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @router.post("/exchange", response_model=None)
    async def exchange(
        request: Request,
        body: NativeExchangeRequest,
        headers: Annotated[BrowserWriteHeaders, Header()],
    ) -> Response:
        if headers.origin != services.browser.public_origin:
            return problem(HTTPStatus.FORBIDDEN, "origin_denied")
        try:
            credential = await services.exchange(
                body.attempt_id, body.verifier, read_cookie(request, SESSION_COOKIE)
            )
        except NativeLoginPendingError:
            return problem(HTTPStatus.CONFLICT, "native_login_pending")
        except (NativeLoginRejectedError, UnauthenticatedError):
            return problem(HTTPStatus.BAD_REQUEST, "native_login_invalid")
        response = Response(status_code=HTTPStatus.NO_CONTENT)
        response.set_cookie(
            SESSION_COOKIE,
            credential.value,
            max_age=COOKIE_LIFETIME,
            secure=True,
            httponly=True,
            samesite="lax",
            path="/",
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    return router
