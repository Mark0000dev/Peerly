"""Unmounted real ban usecase factory; no SQL/default credentials/runtime side effects."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response
from starlette.responses import JSONResponse

from studymate.application.errors import StorageUnavailableError
from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.browser import BrowserTokenSigner
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.lifecycle.ban_ports import LifecycleTargetUnavailableError
from studymate.application.lifecycle.bans import ChangeAccountBan
from studymate.application.lifecycle.commands import ChangeAccountBanCommand
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.domain.lifecycle.states import LifecycleReason
from studymate.presentation.browser import (
    SESSION_AUTH,
    BrowserConfiguration,
    IdempotentWriteHeaders,
    write_credential,
)
from studymate.presentation.lifecycle.ban_models import (
    BanChangeResponse,
    ChangeBanBody,
    ban_response,
)
from studymate.presentation.problems import ProblemResponse, problem

BAN_ERRORS = (
    UnauthenticatedError,
    OperatorAccessDeniedError,
    LifecycleTargetUnavailableError,
    IdempotencyConflictError,
    StorageUnavailableError,
)


@dataclass(frozen=True, slots=True)
class BanHttpServices:
    change_ban: ChangeAccountBan
    signer: BrowserTokenSigner
    browser: BrowserConfiguration


def ban_problem(error: Exception) -> JSONResponse:
    if isinstance(error, StorageUnavailableError):
        response = problem(HTTPStatus.SERVICE_UNAVAILABLE, "storage_unavailable")
        response.headers["Retry-After"] = "1"
        return response
    for kind, status, code in (
        (UnauthenticatedError, HTTPStatus.UNAUTHORIZED, "unauthenticated"),
        (OperatorAccessDeniedError, HTTPStatus.FORBIDDEN, "operator_access_denied"),
        (LifecycleTargetUnavailableError, HTTPStatus.NOT_FOUND, "lifecycle_target_unavailable"),
        (IdempotencyConflictError, HTTPStatus.CONFLICT, "idempotency_conflict"),
    ):
        if isinstance(error, kind):
            return problem(status, code)
    raise error


def ban_router(services: BanHttpServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/operator/accounts",
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

    @router.put("/{account_id}/ban", response_model=BanChangeResponse)
    async def change_ban(
        request: Request,
        response: Response,
        account_id: UUID,
        body: ChangeBanBody,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> BanChangeResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            result = await services.change_ban(
                ChangeAccountBanCommand(
                    credential,
                    account_id,
                    body.banned,
                    LifecycleReason(body.reason),
                    IntentKey(headers.idempotency_key),
                )
            )
        except BAN_ERRORS as error:
            return ban_problem(error)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return ban_response(result)

    return router
