"""Unmounted text HTTP factory. Main composes bounded body/correlation middleware."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Path, Query, Request, Response
from starlette.responses import JSONResponse

from studymate.application.errors import StorageUnavailableError
from studymate.application.idempotency import IntentKey
from studymate.application.identity.browser import BrowserTokenSigner
from studymate.application.media.storage import (
    MediaObjectMissingError,
    MediaStorageUnavailableError,
)
from studymate.application.messaging.commands import (
    CancelMessage,
    CancelMessageCommand,
    ReadMessageOutcome,
    SendMessage,
    SendMessageCommand,
)
from studymate.application.messaging.history import ReadMessageHistory
from studymate.application.messaging.history_cursors import (
    MAX_HISTORY_CURSOR_LENGTH,
    InvalidMessageHistoryCursorError,
)
from studymate.application.messaging.participants import ReadChatAvatar, ReadChatParticipant
from studymate.application.messaging.ports import (
    ClientMessageConflictError,
    ConversationUnavailableError,
    MessageContactUnavailableError,
    MessageImageUnavailableError,
)
from studymate.presentation.browser import (
    SESSION_AUTH,
    SESSION_COOKIE,
    BrowserConfiguration,
    IdempotentWriteHeaders,
    read_cookie,
    write_credential,
)
from studymate.presentation.messaging.models import (
    CancelledOperationResponse,
    ChatParticipantResponse,
    ConfirmedOperationResponse,
    MessageHistoryResponse,
    OperationLookupResponse,
    SendMessageBody,
    TerminalOperationResponse,
    UnobservedOperationResponse,
    history_response,
    participant_response,
    terminal_response,
)
from studymate.presentation.problems import ProblemResponse, problem
from studymate.presentation.student_errors import STUDENT_ERRORS, student_problem

MESSAGE_ERRORS = (
    *STUDENT_ERRORS,
    ConversationUnavailableError,
    MessageContactUnavailableError,
    MessageImageUnavailableError,
    ClientMessageConflictError,
    InvalidMessageHistoryCursorError,
    StorageUnavailableError,
    MediaStorageUnavailableError,
    MediaObjectMissingError,
)


@dataclass(frozen=True, slots=True)
class MessagingHttpServices:
    history: ReadMessageHistory
    send: SendMessage
    cancel: CancelMessage
    outcome: ReadMessageOutcome
    participant: ReadChatParticipant
    avatar: ReadChatAvatar
    signer: BrowserTokenSigner
    browser: BrowserConfiguration


def message_error(error: Exception) -> JSONResponse:
    common = student_problem(error)
    if common is not None:
        return common
    if isinstance(error, (StorageUnavailableError, MediaStorageUnavailableError)):
        response = problem(HTTPStatus.SERVICE_UNAVAILABLE, "messaging_unavailable")
        response.headers["Retry-After"] = "1"
        return response
    for error_type, status, code in (
        (ConversationUnavailableError, HTTPStatus.NOT_FOUND, "conversation_unavailable"),
        (MediaObjectMissingError, HTTPStatus.NOT_FOUND, "chat_avatar_unavailable"),
        (MessageContactUnavailableError, HTTPStatus.CONFLICT, "message_contact_unavailable"),
        (MessageImageUnavailableError, HTTPStatus.CONFLICT, "message_image_unavailable"),
        (ClientMessageConflictError, HTTPStatus.CONFLICT, "client_message_conflict"),
        (
            InvalidMessageHistoryCursorError,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "invalid_message_cursor",
        ),
    ):
        if isinstance(error, error_type):
            return problem(status, code)
    raise error


def private_response(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"


def messaging_router(services: MessagingHttpServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/conversations",
        tags=["messages"],
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

    @router.get("/{conversation_id}/messages", response_model=MessageHistoryResponse)
    async def history(
        request: Request,
        conversation_id: UUID,
        response: Response,
        cursor: Annotated[str | None, Query(max_length=MAX_HISTORY_CURSOR_LENGTH)] = None,
    ) -> MessageHistoryResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = history_response(await services.history(credential, conversation_id, cursor))
        except MESSAGE_ERRORS as error:
            return message_error(error)
        private_response(response)
        return result

    @router.post("/{conversation_id}/messages", response_model=TerminalOperationResponse)
    async def send(
        request: Request,
        conversation_id: UUID,
        body: SendMessageBody,
        response: Response,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> ConfirmedOperationResponse | CancelledOperationResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            result = terminal_response(
                await services.send(
                    SendMessageCommand(
                        credential,
                        conversation_id,
                        body.client_message_id,
                        body.content(),
                        IntentKey(headers.idempotency_key),
                    )
                )
            )
        except MESSAGE_ERRORS as error:
            return message_error(error)
        private_response(response)
        return result

    @router.get(
        "/{conversation_id}/message-operations/{client_message_id}",
        response_model=OperationLookupResponse,
    )
    async def outcome(
        request: Request, conversation_id: UUID, client_message_id: UUID, response: Response
    ) -> (
        ConfirmedOperationResponse
        | CancelledOperationResponse
        | UnobservedOperationResponse
        | Response
    ):
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            actual = await services.outcome(credential, conversation_id, client_message_id)
            result = (
                terminal_response(actual)
                if actual is not None
                else UnobservedOperationResponse(
                    conversation_id=conversation_id, client_message_id=client_message_id
                )
            )
        except MESSAGE_ERRORS as error:
            return message_error(error)
        private_response(response)
        return result

    @router.post(
        "/{conversation_id}/message-operations/{client_message_id}/cancel",
        response_model=TerminalOperationResponse,
    )
    async def cancel(
        request: Request,
        conversation_id: UUID,
        client_message_id: UUID,
        response: Response,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> ConfirmedOperationResponse | CancelledOperationResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        async for chunk in request.stream():
            if chunk:
                return problem(HTTPStatus.UNPROCESSABLE_ENTITY, "cancel_body_not_empty")
        try:
            result = terminal_response(
                await services.cancel(
                    CancelMessageCommand(
                        credential,
                        conversation_id,
                        client_message_id,
                        IntentKey(headers.idempotency_key),
                    )
                )
            )
        except MESSAGE_ERRORS as error:
            return message_error(error)
        private_response(response)
        return result

    @router.get("/{conversation_id}/participant", response_model=ChatParticipantResponse)
    async def participant(
        request: Request, conversation_id: UUID, response: Response
    ) -> ChatParticipantResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = participant_response(await services.participant(credential, conversation_id))
        except MESSAGE_ERRORS as error:
            return message_error(error)
        private_response(response)
        return result

    @router.get(
        "/{conversation_id}/participant/avatar/{photo_version}",
        response_class=Response,
        responses={
            HTTPStatus.OK.value: {
                "content": {"image/jpeg": {"schema": {"type": "string", "format": "binary"}}},
                "description": "Currently authorized processed chat avatar",
            }
        },
    )
    async def avatar(
        request: Request, conversation_id: UUID, photo_version: Annotated[int, Path(ge=1)]
    ) -> Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            data = await services.avatar(credential, conversation_id, photo_version)
        except MESSAGE_ERRORS as error:
            return message_error(error)
        response = Response(data, media_type="image/jpeg")
        private_response(response)
        return response

    return router
