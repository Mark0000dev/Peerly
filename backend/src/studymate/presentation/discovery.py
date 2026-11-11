from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, Response
from starlette.responses import JSONResponse

from studymate.application.discovery.cursors import DiscoveryView, InvalidDiscoveryCursorError
from studymate.application.discovery.deck import ReadDiscoveryDeck
from studymate.application.discovery.passes import (
    ChangePassCommand,
    ChangePrivatePass,
    DiscoveryContextChangedError,
    PassUndoUnavailableError,
    PrivatePassConflictError,
)
from studymate.application.discovery.profiles import DiscoveryProfileUnavailableError
from studymate.application.idempotency import IntentKey
from studymate.application.identity.browser import BrowserTokenSigner
from studymate.domain.discovery import DiscoveryMode
from studymate.presentation.browser import (
    SESSION_AUTH,
    SESSION_COOKIE,
    BrowserConfiguration,
    IdempotentWriteHeaders,
    read_cookie,
    write_credential,
)
from studymate.presentation.discovery_models import (
    ChangePassRequest,
    DiscoveryPageResponse,
    PrivatePassResponse,
    page_response,
    pass_response,
    scope_value,
)
from studymate.presentation.problems import FieldProblem, ProblemResponse, problem
from studymate.presentation.student_errors import STUDENT_ERRORS, student_problem

DISCOVERY_ERRORS = (
    *STUDENT_ERRORS,
    DiscoveryProfileUnavailableError,
    InvalidDiscoveryCursorError,
    DiscoveryContextChangedError,
    PrivatePassConflictError,
    PassUndoUnavailableError,
)


@dataclass(frozen=True, slots=True)
class DiscoveryServices:
    deck: ReadDiscoveryDeck
    change_pass: ChangePrivatePass
    signer: BrowserTokenSigner
    browser: BrowserConfiguration


def _error(error: Exception) -> JSONResponse:
    shared = student_problem(error)
    if shared is not None:
        return shared
    if isinstance(error, InvalidDiscoveryCursorError):
        return problem(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "invalid_cursor",
            errors=(FieldProblem(("query", "cursor"), "invalid_cursor"),),
        )
    if isinstance(error, DiscoveryProfileUnavailableError):
        return problem(HTTPStatus.NOT_FOUND, "person_unavailable")
    if isinstance(error, PrivatePassConflictError):
        return problem(
            HTTPStatus.CONFLICT, "pass_version_conflict", {"current_version": error.current_version}
        )
    if isinstance(error, DiscoveryContextChangedError):
        return problem(HTTPStatus.CONFLICT, "discovery_context_changed")
    if isinstance(error, PassUndoUnavailableError):
        return problem(HTTPStatus.CONFLICT, "pass_undo_unavailable")
    raise RuntimeError("Discovery error has no registered HTTP mapping") from error


def discovery_router(services: DiscoveryServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1",
        tags=["discovery"],
        dependencies=[SESSION_AUTH],
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
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        },
    )

    @router.get("/discovery", response_model=DiscoveryPageResponse)
    async def deck(
        request: Request,
        response: Response,
        mode: DiscoveryMode,
        view: DiscoveryView = DiscoveryView.CANDIDATES,
        cursor: Annotated[str | None, Query(max_length=1024)] = None,
    ) -> DiscoveryPageResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            value = await services.deck(credential, mode, view, cursor)
        except DISCOVERY_ERRORS as error:
            return _error(error)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return page_response(value)

    @router.put("/discovery/passes/{person_id}", response_model=PrivatePassResponse)
    async def change_pass(
        request: Request,
        person_id: UUID,
        body: ChangePassRequest,
        response: Response,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> PrivatePassResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            value = await services.change_pass(
                ChangePassCommand(
                    credential,
                    scope_value(body.context),
                    person_id,
                    body.passed,
                    body.expected_version,
                    IntentKey(headers.idempotency_key),
                    body.undo,
                )
            )
        except DISCOVERY_ERRORS as error:
            return _error(error)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return pass_response(value, person_id)

    return router
