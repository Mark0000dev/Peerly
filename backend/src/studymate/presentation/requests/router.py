"""Unmounted factory; main owns middleware/body bounds, composition and API export."""

from dataclasses import dataclass
from datetime import UTC
from email.utils import format_datetime
from http import HTTPStatus
from typing import Annotated, Literal, Protocol
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, Response
from starlette.responses import JSONResponse

from studymate.application.errors import StorageUnavailableError
from studymate.application.idempotency import IntentKey
from studymate.application.identity.browser import BrowserTokenSigner
from studymate.application.requests.actions import (
    AcceptRequest,
    DeclineRequest,
    RequestAction,
    UndoDecline,
    WithdrawRequest,
)
from studymate.application.requests.cursors import InvalidRequestCursorError
from studymate.application.requests.ports import (
    AcceptedRequest,
    RequestCooldownError,
    RequestSourceChangedError,
    RequestVersionConflictError,
)
from studymate.application.requests.queries import ListRequests, ReadRequest
from studymate.application.requests.send import PreviewRequest, SendRequest
from studymate.application.requests.viewing import AcknowledgeRequestViewed, ViewRequestCommand
from studymate.domain.requests.limits import RequestQuotaError
from studymate.domain.requests.projections import RequestBox, RequestListView
from studymate.domain.requests.states import ConnectionRequest, RequestUnavailableError
from studymate.presentation.browser import (
    SESSION_AUTH,
    SESSION_COOKIE,
    BrowserConfiguration,
    IdempotentWriteHeaders,
    read_cookie,
    write_credential,
)
from studymate.presentation.problems import ProblemResponse, problem
from studymate.presentation.requests.inputs import (
    PreviewRequestBody,
    RequestActionBody,
    SendRequestBody,
    ViewRequestBody,
)
from studymate.presentation.requests.outputs import (
    ConnectedResponse,
    PreviewResponse,
    RequestMutationResponse,
    ViewedResponse,
    accepted_response,
    mutation_response,
    preview_response,
    send_response,
    viewed_response,
)
from studymate.presentation.requests.read_outputs import (
    RequestDetailResponse,
    RequestPageResponse,
    detail_response,
    page_response,
)
from studymate.presentation.student_errors import STUDENT_ERRORS, student_problem

REQUEST_ERRORS = (
    *STUDENT_ERRORS,
    RequestUnavailableError,
    RequestCooldownError,
    RequestSourceChangedError,
    RequestVersionConflictError,
    RequestQuotaError,
    InvalidRequestCursorError,
    StorageUnavailableError,
)


@dataclass(frozen=True, slots=True)
class RequestHttpServices:
    preview: PreviewRequest
    send: SendRequest
    accept: AcceptRequest
    decline: DeclineRequest
    undo: UndoDecline
    withdraw: WithdrawRequest
    listing: ListRequests
    read: ReadRequest
    viewed: AcknowledgeRequestViewed
    signer: BrowserTokenSigner
    browser: BrowserConfiguration


class RequestActionHandler(Protocol):
    async def __call__(self, command: RequestAction) -> ConnectionRequest | AcceptedRequest: ...


def request_error(error: Exception) -> JSONResponse:
    common = student_problem(error)
    if common is not None:
        return common
    if isinstance(error, RequestVersionConflictError):
        return problem(
            HTTPStatus.CONFLICT,
            "request_version_changed",
            {"current_version": error.current_version},
        )
    if isinstance(error, RequestCooldownError):
        response = problem(
            HTTPStatus.CONFLICT, "request_cooldown", {"retry_at": error.until.isoformat()}
        )
        response.headers["Retry-After"] = format_datetime(error.until.astimezone(UTC), usegmt=True)
        return response
    if isinstance(error, StorageUnavailableError):
        response = problem(HTTPStatus.SERVICE_UNAVAILABLE, "storage_unavailable")
        response.headers["Retry-After"] = "1"
        return response
    for error_type, status, code in (
        (RequestUnavailableError, HTTPStatus.NOT_FOUND, "request_unavailable"),
        (RequestSourceChangedError, HTTPStatus.CONFLICT, "request_source_changed"),
        (RequestQuotaError, HTTPStatus.TOO_MANY_REQUESTS, "request_quota_exceeded"),
        (InvalidRequestCursorError, HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_request_cursor"),
    ):
        if isinstance(error, error_type):
            return problem(status, code)
    raise error


def private_response(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"


@dataclass(frozen=True, slots=True)
class HttpRequestAction:
    services: RequestHttpServices
    handler: RequestActionHandler
    outcome: Literal["accepted", "declined", "undo_decline", "withdrawn"]

    async def __call__(
        self,
        request: Request,
        request_id: UUID,
        body: RequestActionBody,
        response: Response,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> RequestMutationResponse | Response:
        credential = await write_credential(
            request, self.services.signer, self.services.browser, headers
        )
        if isinstance(credential, JSONResponse):
            return credential
        try:
            result = await self.handler(
                RequestAction(
                    credential,
                    body.person_id,
                    request_id,
                    body.expected_version,
                    IntentKey(headers.idempotency_key),
                )
            )
            private_response(response)
            return (
                accepted_response(result)
                if isinstance(result, AcceptedRequest)
                else mutation_response(result, self.outcome)
            )
        except REQUEST_ERRORS as error:
            return request_error(error)


def requests_router(services: RequestHttpServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/requests",
        tags=["requests"],
        dependencies=[SESSION_AUTH],
        responses={
            status.value: {"model": ProblemResponse}
            for status in (
                HTTPStatus.UNAUTHORIZED,
                HTTPStatus.FORBIDDEN,
                HTTPStatus.NOT_FOUND,
                HTTPStatus.CONFLICT,
                HTTPStatus.UNPROCESSABLE_ENTITY,
                HTTPStatus.TOO_MANY_REQUESTS,
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        },
    )

    @router.get("", response_model=RequestPageResponse)
    async def listing(
        request: Request,
        response: Response,
        box: RequestBox = RequestBox.RECEIVED,
        view: RequestListView = RequestListView.ACTIVE,
        cursor: Annotated[str | None, Query(max_length=1024)] = None,
    ) -> RequestPageResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        if box == RequestBox.SENT and view == RequestListView.RECENTLY_DECLINED:
            return problem(HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_request_view")
        try:
            result = page_response(
                await services.listing(credential, box, view, cursor), services.send.limits
            )
        except REQUEST_ERRORS as error:
            return request_error(error)
        private_response(response)
        return result

    @router.get("/{request_id}", response_model=RequestDetailResponse)
    async def detail(
        request: Request, request_id: UUID, response: Response
    ) -> RequestDetailResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = detail_response(await services.read(credential, request_id))
        except REQUEST_ERRORS as error:
            return request_error(error)
        private_response(response)
        return result

    @router.post(
        "/preview", response_model=PreviewResponse | RequestMutationResponse | ConnectedResponse
    )
    async def preview(
        request: Request,
        body: PreviewRequestBody,
        response: Response,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> PreviewResponse | RequestMutationResponse | ConnectedResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            result = preview_response(
                await services.preview.for_composer(
                    credential,
                    body.person_id,
                    body.mode,
                    IntentKey(headers.idempotency_key),
                    services.send.limits,
                )
            )
        except REQUEST_ERRORS as error:
            return request_error(error)
        private_response(response)
        return result

    @router.post("", response_model=RequestMutationResponse | ConnectedResponse)
    async def send(
        request: Request,
        body: SendRequestBody,
        response: Response,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> RequestMutationResponse | ConnectedResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            result = send_response(
                await services.send(
                    credential,
                    body.person_id,
                    body.preview_id,
                    body.message(),
                    IntentKey(headers.idempotency_key),
                )
            )
        except REQUEST_ERRORS as error:
            return request_error(error)
        private_response(response)
        return result

    @router.post("/{request_id}/viewed", response_model=ViewedResponse)
    async def viewed(
        request: Request,
        request_id: UUID,
        body: ViewRequestBody,
        response: Response,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> ViewedResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            result = viewed_response(
                await services.viewed(
                    ViewRequestCommand(
                        credential,
                        request_id,
                        body.disclosure_id,
                        IntentKey(headers.idempotency_key),
                    )
                )
            )
        except REQUEST_ERRORS as error:
            return request_error(error)
        private_response(response)
        return result

    actions: tuple[
        tuple[
            str, RequestActionHandler, Literal["accepted", "declined", "undo_decline", "withdrawn"]
        ],
        ...,
    ] = (
        ("accept", services.accept, "accepted"),
        ("decline", services.decline, "declined"),
        ("undo-decline", services.undo, "undo_decline"),
        ("withdraw", services.withdraw, "withdrawn"),
    )
    for path, handler, outcome in actions:
        action_route = HttpRequestAction(services, handler, outcome)
        router.add_api_route(
            "/{request_id}/" + path,
            action_route,
            methods=["POST"],
            response_model=RequestMutationResponse,
        )
    return router
