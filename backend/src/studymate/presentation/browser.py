from dataclasses import dataclass
from http import HTTPStatus
from urllib.parse import urlsplit

from fastapi import Depends, Request
from fastapi.security import APIKeyCookie
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse, Response

from studymate.application.identity.browser import BrowserTokenSigner
from studymate.application.identity.sessions import SessionCredential, UnauthenticatedError
from studymate.presentation.problems import problem

SESSION_COOKIE = "__Host-studymate_session"
SESSION_AUTH = Depends(
    APIKeyCookie(name=SESSION_COOKIE, scheme_name="SessionCookie", auto_error=False)
)


def clear_session_cookie(response: Response) -> None:
    """Retire only the application session; separate recovery proofs retain their scope."""
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="lax")


@dataclass(frozen=True, slots=True)
class BrowserConfiguration:
    public_origin: str
    trusted_origins: frozenset[str]

    def __post_init__(self) -> None:
        for origin in self.trusted_origins | {self.public_origin}:
            parsed = urlsplit(origin)
            if (
                parsed.scheme != "https"
                or not parsed.netloc
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username is not None
            ):
                raise ValueError("Browser origins must be explicit HTTPS origins without paths")
        if self.public_origin not in self.trusted_origins:
            raise ValueError("Public origin must be trusted")


def read_cookie(request: Request, name: str) -> SessionCredential | None:
    value = request.cookies.get(name)
    if value is None:
        return None
    try:
        return SessionCredential(value)
    except UnauthenticatedError:
        return None


class BrowserWriteHeaders(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    origin: str | None = Field(
        default=None,
        description="Browser supplies a trusted Origin; missing/foreign Origin is rejected.",
    )
    x_csrf_token: str | None = Field(
        default=None,
        description="Required for cookie-authenticated writes; obtain csrf_token from GET /me.",
    )


class IdempotentWriteHeaders(BrowserWriteHeaders):
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9_-]{8,128}$")


async def write_credential(
    request: Request,
    signer: BrowserTokenSigner,
    browser: BrowserConfiguration,
    headers: BrowserWriteHeaders,
) -> SessionCredential | JSONResponse:
    credential = read_cookie(request, SESSION_COOKIE)
    if credential is None:
        return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
    if headers.origin not in browser.trusted_origins:
        return problem(HTTPStatus.FORBIDDEN, "origin_denied")
    if not await signer.valid_csrf(credential, headers.x_csrf_token or ""):
        return problem(HTTPStatus.FORBIDDEN, "csrf_denied")
    return credential
