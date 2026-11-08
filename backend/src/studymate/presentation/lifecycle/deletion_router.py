"""Unmounted deletion command transport; main owns preflight/status proof and SQL effects."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Header, Request, Response
from starlette.responses import JSONResponse

from studymate.application.errors import StorageUnavailableError
from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.browser import BrowserTokenSigner
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.lifecycle.ban_ports import LifecycleTargetUnavailableError
from studymate.application.lifecycle.commands import DeleteOwnAccountCommand
from studymate.application.lifecycle.deletion_ports import DeletionWorkflowUnavailableError
from studymate.application.lifecycle.deletions import DeleteOwnAccount
from studymate.presentation.browser import (
    SESSION_AUTH,
    BrowserConfiguration,
    IdempotentWriteHeaders,
    clear_session_cookie,
    write_credential,
)
from studymate.presentation.lifecycle.deletion_models import (
    DeleteAccountBody,
    DeletionReceiptResponse,
    deletion_response,
)
from studymate.presentation.problems import ProblemResponse, problem

DELETION_ERRORS = (
    UnauthenticatedError,
    LifecycleTargetUnavailableError,
    DeletionWorkflowUnavailableError,
    IdempotencyConflictError,
    StorageUnavailableError,
)


@dataclass(frozen=True, slots=True)
class DeletionHttpServices:
    delete_account: DeleteOwnAccount
    signer: BrowserTokenSigner
    browser: BrowserConfiguration


def deletion_problem(error: Exception) -> JSONResponse:
    if isinstance(error, StorageUnavailableError):
        response = problem(HTTPStatus.SERVICE_UNAVAILABLE, "storage_unavailable")
        response.headers["Retry-After"] = "1"
        return response
    for kind, status, code in (
        (UnauthenticatedError, HTTPStatus.UNAUTHORIZED, "unauthenticated"),
        (LifecycleTargetUnavailableError, HTTPStatus.NOT_FOUND, "lifecycle_target_unavailable"),
        (DeletionWorkflowUnavailableError, HTTPStatus.NOT_FOUND, "deletion_workflow_unavailable"),
        (IdempotencyConflictError, HTTPStatus.CONFLICT, "idempotency_conflict"),
    ):
        if isinstance(error, kind):
            return problem(status, code)
    raise error


def deletion_router(services: DeletionHttpServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/me",
        tags=["lifecycle"],
        dependencies=[SESSION_AUTH],
        responses={
            status.value: {"model": ProblemResponse}
            for status in (
                HTTPStatus.UNAUTHORIZED,
                HTTPStatus.FORBIDDEN,
                HTTPStatus.NOT_FOUND,
                HTTPStatus.CONFLICT,
                HTTPStatus.UNPROCESSABLE_ENTITY,
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        },
    )

    @router.post("/deletion", response_model=DeletionReceiptResponse)
    async def delete_account(
        request: Request,
        response: Response,
        body: DeleteAccountBody,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> DeletionReceiptResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            result = await services.delete_account(
                DeleteOwnAccountCommand(
                    credential,
                    body.workflow_id,
                    IntentKey(headers.idempotency_key),
                )
            )
        except DELETION_ERRORS as error:
            return deletion_problem(error)
        # Actual shared hook clears ONLY the existing session; no CSRF cookie exists.
        # Main's separate future outcome proof must remain untouched.
        clear_session_cookie(response)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return deletion_response(result)

    return router
