from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Header, Query, Request
from starlette.responses import JSONResponse, Response

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.browser import BrowserTokenSigner
from studymate.application.identity.registration import (
    BeginRegistration,
    BeginRegistrationCommand,
    CompleteRegistration,
    CompleteRegistrationCommand,
    PolicyDocumentUnavailableError,
    ReadPolicyStatus,
    ReadPublishedPolicy,
    RegistrationActionDeniedError,
    RegistrationAlreadyCompletedError,
    RegistrationContextUnavailableError,
    RegistrationDocumentsUnavailableError,
    RegistrationSetupIncompleteError,
)
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.domain.registration import PolicyKind, PolicyVersion
from studymate.presentation.browser import (
    SESSION_AUTH,
    SESSION_COOKIE,
    BrowserConfiguration,
    IdempotentWriteHeaders,
    read_cookie,
    write_credential,
)
from studymate.presentation.problems import FieldProblem, ProblemResponse, problem
from studymate.presentation.registration_models import (
    CompleteRegistrationRequest,
    PolicyStatusResponse,
    PublishedPolicyResponse,
    RegistrationContextResponse,
    RegistrationReceiptResponse,
    context_response,
    policy_reference,
    receipt_response,
)


@dataclass(frozen=True, slots=True)
class RegistrationServices:
    begin: BeginRegistration
    complete: CompleteRegistration
    status: ReadPolicyStatus
    document: ReadPublishedPolicy
    signer: BrowserTokenSigner
    browser: BrowserConfiguration


def _registration_error(error: Exception) -> JSONResponse:
    if isinstance(error, (UnauthenticatedError, RegistrationActionDeniedError)):
        return problem(
            HTTPStatus.UNAUTHORIZED
            if isinstance(error, UnauthenticatedError)
            else HTTPStatus.FORBIDDEN,
            "unauthenticated"
            if isinstance(error, UnauthenticatedError)
            else "registration_not_allowed",
        )
    if isinstance(error, RegistrationDocumentsUnavailableError):
        return problem(HTTPStatus.SERVICE_UNAVAILABLE, "registration_documents_unavailable")
    if isinstance(error, IdempotencyConflictError):
        return problem(HTTPStatus.CONFLICT, "idempotency_conflict")
    if isinstance(error, RegistrationAlreadyCompletedError):
        return problem(HTTPStatus.CONFLICT, "registration_already_completed")
    if isinstance(error, RegistrationContextUnavailableError):
        return problem(HTTPStatus.CONFLICT, "registration_context_unavailable")
    return _registration_setup_error(error)


def _registration_setup_error(error: Exception) -> JSONResponse:
    if isinstance(error, RegistrationSetupIncompleteError):
        return problem(
            HTTPStatus.CONFLICT,
            "onboarding_incomplete",
            errors=tuple(
                FieldProblem(("onboarding", requirement.value), "required")
                for requirement in error.requirements
            ),
        )
    raise error


def registration_router(services: RegistrationServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1",
        tags=["registration"],
        responses={
            status.value: {"model": ProblemResponse}
            for status in (
                HTTPStatus.BAD_REQUEST,
                HTTPStatus.UNAUTHORIZED,
                HTTPStatus.FORBIDDEN,
                HTTPStatus.NOT_FOUND,
                HTTPStatus.CONFLICT,
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                HTTPStatus.UNPROCESSABLE_ENTITY,
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        },
    )
    router.include_router(_public_policy_router(services))
    router.include_router(_private_registration_router(services))
    return router


def _public_policy_router(services: RegistrationServices) -> APIRouter:
    router = APIRouter()

    @router.get("/policies/{kind}", response_model=PublishedPolicyResponse)
    async def policy(
        kind: PolicyKind,
        response: Response,
        version: Annotated[str | None, Query(pattern=r"^[A-Za-z0-9._-]{1,64}$")] = None,
    ) -> PublishedPolicyResponse | Response:
        try:
            document = await services.document(
                kind, PolicyVersion(version) if version is not None else None
            )
        except PolicyDocumentUnavailableError:
            return problem(HTTPStatus.NOT_FOUND, "policy_document_unavailable")
        response.headers["Cache-Control"] = "public, max-age=60"
        return PublishedPolicyResponse(
            reference=policy_reference(document.reference),
            title=document.title,
            content=document.content,
        )

    return router


def _private_registration_router(services: RegistrationServices) -> APIRouter:
    router = APIRouter(dependencies=[SESSION_AUTH])

    @router.get("/me/policy-status", response_model=PolicyStatusResponse)
    async def status(request: Request, response: Response) -> PolicyStatusResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.status(credential)
        except UnauthenticatedError as error:
            return _registration_error(error)
        response.headers["Cache-Control"] = "no-store"
        return PolicyStatusResponse(
            receipt=receipt_response(result.receipt) if result.receipt is not None else None,
            current_terms=policy_reference(result.current_terms)
            if result.current_terms is not None
            else None,
            current_privacy=policy_reference(result.current_privacy)
            if result.current_privacy is not None
            else None,
        )

    @router.post(
        "/me/registration-context",
        status_code=HTTPStatus.CREATED,
        response_model=RegistrationContextResponse,
    )
    async def begin(
        request: Request, response: Response, headers: Annotated[IdempotentWriteHeaders, Header()]
    ) -> RegistrationContextResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            context = await services.begin(
                BeginRegistrationCommand(credential, IntentKey(headers.idempotency_key))
            )
        except (
            UnauthenticatedError,
            RegistrationActionDeniedError,
            RegistrationDocumentsUnavailableError,
            IdempotencyConflictError,
            RegistrationAlreadyCompletedError,
        ) as error:
            return _registration_error(error)
        response.headers["Cache-Control"] = "no-store"
        return context_response(context)

    @router.post("/me/registration", response_model=RegistrationReceiptResponse)
    async def complete(
        request: Request,
        body: CompleteRegistrationRequest,
        response: Response,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> RegistrationReceiptResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            receipt = await services.complete(
                CompleteRegistrationCommand(
                    credential, body.context_id, IntentKey(headers.idempotency_key)
                )
            )
        except (
            UnauthenticatedError,
            RegistrationActionDeniedError,
            RegistrationContextUnavailableError,
            RegistrationSetupIncompleteError,
            IdempotencyConflictError,
        ) as error:
            return _registration_error(error)
        response.headers["Cache-Control"] = "no-store"
        return receipt_response(receipt)

    return router
