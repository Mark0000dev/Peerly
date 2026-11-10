from dataclasses import dataclass
from http import HTTPStatus
from ipaddress import ip_address
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.security import APIKeyCookie
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from starlette.responses import JSONResponse

from studymate.application.errors import StorageUnavailableError
from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.browser import BrowserTokenSigner
from studymate.application.identity.sessions import SessionCredential, UnauthenticatedError
from studymate.application.support.cases import (
    CreateSupportCase,
    CreateSupportCommand,
    PrepareSupport,
    ReadActorSupportCase,
    ReadRecentActorSupportCases,
    ReadRecentSupportCases,
    ReadSupportCase,
    SupportCredential,
    SupportQuotaError,
    SupportUnavailableError,
)
from studymate.domain.support.cases import (
    SupportContent,
    SupportReceipt,
    SupportStatus,
    SupportTopic,
)
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

SUPPORT_COOKIE = "__Host-peerly_support"
SUPPORT_AUTH = Depends(
    APIKeyCookie(name=SUPPORT_COOKIE, scheme_name="SupportProofCookie", auto_error=False)
)
SUPPORT_ERRORS = (
    SupportUnavailableError,
    SupportQuotaError,
    UnauthenticatedError,
    IdempotencyConflictError,
    StorageUnavailableError,
)


class SupportPreparationBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SupportPreparationResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    csrf_token: str = Field(repr=False)
    expires_at: AwareDatetime


class SupportBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    topic: SupportTopic
    reply_address: str = Field(min_length=3, max_length=254, repr=False)
    message: str = Field(min_length=1, max_length=4000, repr=False)
    details: str | None = Field(default=None, min_length=1, max_length=2000, repr=False)

    @model_validator(mode="after")
    def valid_content(self) -> "SupportBody":
        self.content()
        return self

    def content(self) -> SupportContent:
        return SupportContent(self.topic, self.reply_address, self.message, self.details)


class SupportReceiptResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    case_id: UUID
    status: SupportStatus
    version: int = Field(ge=1)
    received_at: AwareDatetime
    changed_at: AwareDatetime


class RecentSupportCasesResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    cases: tuple[SupportReceiptResponse, ...] = Field(max_length=20)


def support_response(receipt: SupportReceipt) -> SupportReceiptResponse:
    return SupportReceiptResponse(
        case_id=receipt.case_id,
        status=receipt.status,
        version=receipt.version,
        received_at=receipt.received_at,
        changed_at=receipt.changed_at,
    )


@dataclass(frozen=True, slots=True)
class SupportHttpServices:
    prepare: PrepareSupport
    create: CreateSupportCase
    read: ReadSupportCase
    actor_read: ReadActorSupportCase
    signer: BrowserTokenSigner
    browser: BrowserConfiguration
    recent: ReadRecentSupportCases
    actor_recent: ReadRecentActorSupportCases


def support_problem(error: Exception) -> JSONResponse:
    if isinstance(error, SupportUnavailableError):
        return problem(HTTPStatus.NOT_FOUND, "support_unavailable")
    if isinstance(error, UnauthenticatedError):
        return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
    if isinstance(error, IdempotencyConflictError):
        return problem(HTTPStatus.CONFLICT, "idempotency_conflict")
    if isinstance(error, SupportQuotaError):
        response = problem(HTTPStatus.TOO_MANY_REQUESTS, "support_quota_exceeded")
        response.headers["Retry-After"] = "3600"
        return response
    if isinstance(error, StorageUnavailableError):
        response = problem(HTTPStatus.SERVICE_UNAVAILABLE, "storage_unavailable")
        response.headers["Retry-After"] = "1"
        return response
    raise error


def _credential(request: Request) -> SupportCredential | None:
    value = request.cookies.get(SUPPORT_COOKIE)
    if value is None:
        return None
    try:
        return SupportCredential(value)
    except SupportUnavailableError:
        return None


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"


def support_router(services: SupportHttpServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1",
        tags=["support"],
        responses={
            code: {"model": ProblemResponse} for code in (401, 403, 404, 409, 422, 429, 503)
        },
    )

    @router.post("/support-context", response_model=SupportPreparationResponse)
    async def prepare(
        request: Request,
        response: Response,
        _body: SupportPreparationBody,
        headers: Annotated[BrowserWriteHeaders, Header()],
    ) -> SupportPreparationResponse | Response:
        # Public context issuance has no write authority. Require the exact first-party
        # origin, JSON body, and observed network peer, never an arbitrary forwarded IP.
        if headers.origin != services.browser.public_origin:
            return problem(HTTPStatus.FORBIDDEN, "origin_denied")
        if request.client is None:
            return problem(HTTPStatus.FORBIDDEN, "source_unavailable")
        try:
            source = str(ip_address(request.client.host))
        except ValueError:
            return problem(HTTPStatus.FORBIDDEN, "source_unavailable")
        try:
            proof, expiry = await services.prepare(
                await services.signer.source_digest(source), _credential(request)
            )
        except SUPPORT_ERRORS as error:
            return support_problem(error)
        response.set_cookie(
            SUPPORT_COOKIE,
            proof.value,
            expires=expiry,
            path="/",
            secure=True,
            httponly=True,
            samesite="strict",
        )
        _private(response)
        # Only syntax is shared with the signer; this credential is NEVER passed to
        # identity lookup, session minting, or deletion status authorization.
        csrf = await services.signer.csrf_token(SessionCredential(proof.value))
        return SupportPreparationResponse(csrf_token=csrf, expires_at=expiry)

    @router.post(
        "/support-cases",
        response_model=SupportReceiptResponse,
        status_code=HTTPStatus.CREATED,
        dependencies=[SUPPORT_AUTH],
    )
    async def create(
        request: Request,
        response: Response,
        body: SupportBody,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> SupportReceiptResponse | Response:
        if headers.origin != services.browser.public_origin:
            return problem(HTTPStatus.FORBIDDEN, "origin_denied")
        proof = _credential(request)
        if proof is None:
            return problem(HTTPStatus.NOT_FOUND, "support_unavailable")
        if not await services.signer.valid_csrf(
            SessionCredential(proof.value), headers.x_csrf_token or ""
        ):
            return problem(HTTPStatus.FORBIDDEN, "csrf_denied")
        # Public proof owns the case. Identity binding is available separately using
        # the actual session guard; absent binding does not imply an account lookup.
        try:
            receipt = await services.create(
                CreateSupportCommand(proof, body.content(), IntentKey(headers.idempotency_key))
            )
        except SUPPORT_ERRORS as error:
            return support_problem(error)
        _private(response)
        return support_response(receipt)

    @router.get(
        "/support-cases/{case_id}",
        response_model=SupportReceiptResponse,
        dependencies=[SUPPORT_AUTH],
    )
    async def read(
        case_id: UUID, request: Request, response: Response
    ) -> SupportReceiptResponse | Response:
        proof = _credential(request)
        if proof is None:
            return problem(HTTPStatus.NOT_FOUND, "support_unavailable")
        try:
            receipt = await services.read(proof, case_id)
        except SUPPORT_ERRORS as error:
            return support_problem(error)
        _private(response)
        return support_response(receipt)

    @router.get(
        "/me/support-cases/{case_id}",
        response_model=SupportReceiptResponse,
        dependencies=[SESSION_AUTH],
    )
    async def actor_read(
        case_id: UUID, request: Request, response: Response
    ) -> SupportReceiptResponse | Response:
        session = read_cookie(request, SESSION_COOKIE)
        if session is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            receipt = await services.actor_read(session, case_id)
        except SUPPORT_ERRORS as error:
            return support_problem(error)
        _private(response)
        return support_response(receipt)

    @router.post(
        "/me/support-cases",
        response_model=SupportReceiptResponse,
        status_code=HTTPStatus.CREATED,
        dependencies=[SESSION_AUTH, SUPPORT_AUTH],
    )
    async def actor_create(
        request: Request,
        response: Response,
        body: SupportBody,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> SupportReceiptResponse | Response:
        session = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(session, JSONResponse):
            return session
        proof = _credential(request)
        if proof is None:
            return problem(HTTPStatus.NOT_FOUND, "support_unavailable")
        try:
            receipt = await services.create(
                CreateSupportCommand(
                    proof, body.content(), IntentKey(headers.idempotency_key), session
                )
            )
        except SUPPORT_ERRORS as error:
            return support_problem(error)
        _private(response)
        return support_response(receipt)

    router.include_router(recent_support_router(services))
    return router


def recent_support_router(services: SupportHttpServices) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/support-cases", response_model=RecentSupportCasesResponse, dependencies=[SUPPORT_AUTH]
    )
    async def recent(request: Request, response: Response) -> RecentSupportCasesResponse | Response:
        proof = _credential(request)
        if proof is None:
            return problem(HTTPStatus.NOT_FOUND, "support_unavailable")
        try:
            receipts = await services.recent(proof)
        except SUPPORT_ERRORS as error:
            return support_problem(error)
        _private(response)
        return RecentSupportCasesResponse(cases=tuple(support_response(item) for item in receipts))

    @router.get(
        "/me/support-cases", response_model=RecentSupportCasesResponse, dependencies=[SESSION_AUTH]
    )
    async def actor_recent(
        request: Request, response: Response
    ) -> RecentSupportCasesResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            receipts = await services.actor_recent(credential)
        except SUPPORT_ERRORS as error:
            return support_problem(error)
        _private(response)
        return RecentSupportCasesResponse(cases=tuple(support_response(item) for item in receipts))

    return router
