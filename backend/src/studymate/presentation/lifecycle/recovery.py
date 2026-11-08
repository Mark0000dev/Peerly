"""Narrow deletion status cookie survives normal application-session retirement."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.security import APIKeyCookie
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.browser import BrowserTokenSigner
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.lifecycle.recovery import (
    DeletionStatusCredential,
    DeletionStatusUnavailableError,
    PrepareOwnDeletion,
    ReadOwnDeletionStatus,
)
from studymate.presentation.browser import (
    SESSION_AUTH,
    BrowserConfiguration,
    BrowserWriteHeaders,
    write_credential,
)
from studymate.presentation.problems import ProblemResponse, problem

DELETION_STATUS_COOKIE = "__Host-peerly_deletion_status"
DELETION_STATUS_AUTH = Depends(
    APIKeyCookie(name=DELETION_STATUS_COOKIE, scheme_name="DeletionStatusCookie", auto_error=False)
)
RECOVERY_ERRORS = (UnauthenticatedError, DeletionStatusUnavailableError, StorageUnavailableError)


class DeletionPreparationBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DeletionPreparationResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    workflow_id: UUID
    expires_at: AwareDatetime


class PendingDeletionResponse(DeletionPreparationResponse):
    state: Literal["pending"] = "pending"


class ConfirmedDeletionResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    state: Literal["deleted"] = "deleted"
    workflow_id: UUID
    deleted_at: AwareDatetime
    source_version: int = Field(ge=1)


DeletionStatusResponse = Annotated[
    PendingDeletionResponse | ConfirmedDeletionResponse, Field(discriminator="state")
]


@dataclass(frozen=True, slots=True)
class DeletionRecoveryHttpServices:
    prepare: PrepareOwnDeletion
    status: ReadOwnDeletionStatus
    signer: BrowserTokenSigner
    browser: BrowserConfiguration


def recovery_problem(error: Exception) -> JSONResponse:
    if isinstance(error, StorageUnavailableError):
        response = problem(HTTPStatus.SERVICE_UNAVAILABLE, "storage_unavailable")
        response.headers["Retry-After"] = "1"
        return response
    if isinstance(error, UnauthenticatedError):
        return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
    if isinstance(error, DeletionStatusUnavailableError):
        return problem(HTTPStatus.NOT_FOUND, "deletion_status_unavailable")
    raise error


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"


def deletion_recovery_router(services: DeletionRecoveryHttpServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/me",
        tags=["lifecycle"],
        responses={
            status.value: {"model": ProblemResponse}
            for status in (
                HTTPStatus.UNAUTHORIZED,
                HTTPStatus.FORBIDDEN,
                HTTPStatus.NOT_FOUND,
                HTTPStatus.UNPROCESSABLE_ENTITY,
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        },
    )

    @router.post(
        "/deletion-workflows",
        response_model=DeletionPreparationResponse,
        dependencies=[SESSION_AUTH],
    )
    async def prepare(
        request: Request,
        response: Response,
        _body: DeletionPreparationBody,
        headers: Annotated[BrowserWriteHeaders, Header()],
    ) -> DeletionPreparationResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            prepared = await services.prepare(credential)
        except RECOVERY_ERRORS as error:
            return recovery_problem(error)
        authorization = prepared.authorization
        response.set_cookie(
            DELETION_STATUS_COOKIE,
            prepared.status_credential.value,
            expires=authorization.expires_at,
            path="/",
            secure=True,
            httponly=True,
            samesite="strict",
        )
        _private(response)
        return DeletionPreparationResponse(
            workflow_id=authorization.id, expires_at=authorization.expires_at
        )

    @router.get(
        "/deletion-status",
        response_model=DeletionStatusResponse,
        dependencies=[DELETION_STATUS_AUTH],
    )
    async def status(
        request: Request, response: Response
    ) -> PendingDeletionResponse | ConfirmedDeletionResponse | Response:
        value = request.cookies.get(DELETION_STATUS_COOKIE)
        if value is None:
            return problem(HTTPStatus.NOT_FOUND, "deletion_status_unavailable")
        try:
            credential = DeletionStatusCredential(value)
        except ValueError:
            return problem(HTTPStatus.NOT_FOUND, "deletion_status_unavailable")
        try:
            result = await services.status(credential)
        except RECOVERY_ERRORS as error:
            return recovery_problem(error)
        _private(response)
        if result.deletion is None:
            return PendingDeletionResponse(
                workflow_id=result.authorization.id, expires_at=result.authorization.expires_at
            )
        source = result.deletion
        return ConfirmedDeletionResponse(
            workflow_id=source.workflow_id,
            deleted_at=source.deleted_at,
            source_version=source.version,
        )

    return router
