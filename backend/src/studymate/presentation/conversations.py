"""Participant-scoped conversation detail and explicit private read acknowledgement."""

from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from studymate.application.idempotency import IntentKey
from studymate.application.identity.browser import BrowserTokenSigner
from studymate.application.messaging.conversation_details import (
    ConversationDetails,
    ReadConversationDetails,
)
from studymate.application.messaging.conversation_list import (
    CONVERSATION_CURSOR_LIMIT,
    ConversationListPage,
    InvalidConversationCursorError,
    ListConversations,
)
from studymate.application.messaging.read_positions import (
    AcknowledgeConversationRead,
    ReadPositionCommand,
    ReadSequenceUnavailableError,
)
from studymate.domain.message_reads import ConversationReadPosition
from studymate.presentation.browser import (
    SESSION_AUTH,
    SESSION_COOKIE,
    BrowserConfiguration,
    IdempotentWriteHeaders,
    read_cookie,
    write_credential,
)
from studymate.presentation.messaging.models import (
    ChatParticipantResponse,
    MessageResponse,
    message_response,
    participant_response,
)
from studymate.presentation.messaging.router import MESSAGE_ERRORS, message_error, private_response
from studymate.presentation.problems import ProblemResponse, problem
from studymate.presentation.requests.outputs import AcademicContextResponse, academic_context


class ConversationReadPositionBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    through_sequence: int = Field(strict=True, ge=1, le=9223372036854775806)


class ConversationReadPositionResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    conversation_id: UUID
    version: int
    through_sequence: int
    acknowledged_at: datetime


class ConversationDetailsResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    conversation_id: UUID
    request_id: UUID
    accepted_request_version: int
    accepted_at: datetime
    peer: ChatParticipantResponse = Field(repr=False)
    original_context: AcademicContextResponse = Field(repr=False)
    last_confirmed_sequence: int
    read_position: ConversationReadPositionResponse | None
    unread_count: int
    can_send: bool


def read_position_response(value: ConversationReadPosition) -> ConversationReadPositionResponse:
    return ConversationReadPositionResponse(
        conversation_id=value.conversation_id,
        version=value.version,
        through_sequence=value.through_sequence,
        acknowledged_at=value.acknowledged_at,
    )


def conversation_details_response(value: ConversationDetails) -> ConversationDetailsResponse:
    return ConversationDetailsResponse(
        conversation_id=value.conversation.id,
        request_id=value.accepted_request.id,
        accepted_request_version=value.accepted_request.version,
        accepted_at=value.accepted_request.changed_at,
        peer=participant_response(value.peer),
        original_context=academic_context(value.accepted_request.context),
        last_confirmed_sequence=value.conversation.next_message_sequence - 1,
        read_position=(
            read_position_response(value.read_position) if value.read_position is not None else None
        ),
        unread_count=value.unread_count,
        can_send=value.can_send,
    )


class ConversationSummaryResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    conversation_id: UUID
    request_id: UUID
    accepted_at: datetime
    activity_at: datetime
    peer: ChatParticipantResponse = Field(repr=False)
    original_context: AcademicContextResponse = Field(repr=False)
    last_message: MessageResponse | None = Field(repr=False)
    unread_count: int
    can_send: bool


class ConversationListResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    conversations: tuple[ConversationSummaryResponse, ...] = Field(repr=False)
    next_cursor: str | None


def conversation_list_response(value: ConversationListPage) -> ConversationListResponse:
    return ConversationListResponse(
        conversations=tuple(
            ConversationSummaryResponse(
                conversation_id=row.conversation_id,
                request_id=row.request_id,
                accepted_at=row.accepted_at,
                activity_at=row.activity_at,
                peer=participant_response(row.peer),
                original_context=academic_context(row.original_context),
                last_message=message_response(row.last_message)
                if row.last_message is not None
                else None,
                unread_count=row.unread_count,
                can_send=row.can_send,
            )
            for row in value.conversations
        ),
        next_cursor=value.next_cursor,
    )


@dataclass(frozen=True, slots=True)
class ConversationsHttpServices:
    listing: ListConversations
    details: ReadConversationDetails
    acknowledge: AcknowledgeConversationRead
    signer: BrowserTokenSigner
    browser: BrowserConfiguration


def conversations_router(services: ConversationsHttpServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/conversations",
        tags=["conversations"],
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

    @router.get("", response_model=ConversationListResponse)
    async def listing(
        request: Request,
        response: Response,
        cursor: Annotated[str | None, Query(max_length=CONVERSATION_CURSOR_LIMIT)] = None,
    ) -> ConversationListResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = conversation_list_response(await services.listing(credential, cursor))
        except InvalidConversationCursorError:
            return problem(HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_conversation_cursor")
        except MESSAGE_ERRORS as error:
            return message_error(error)
        private_response(response)
        return result

    @router.get("/{conversation_id}", response_model=ConversationDetailsResponse)
    async def details(
        request: Request, conversation_id: UUID, response: Response
    ) -> ConversationDetailsResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = conversation_details_response(
                await services.details(credential, conversation_id)
            )
        except MESSAGE_ERRORS as error:
            return message_error(error)
        private_response(response)
        return result

    @router.put("/{conversation_id}/read-position", response_model=ConversationReadPositionResponse)
    async def acknowledge(
        request: Request,
        conversation_id: UUID,
        body: ConversationReadPositionBody,
        response: Response,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> ConversationReadPositionResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            result = read_position_response(
                await services.acknowledge(
                    ReadPositionCommand(
                        credential,
                        conversation_id,
                        body.through_sequence,
                        IntentKey(headers.idempotency_key),
                    )
                )
            )
        except ReadSequenceUnavailableError:
            return problem(HTTPStatus.CONFLICT, "conversation_read_sequence_unavailable")
        except MESSAGE_ERRORS as error:
            return message_error(error)
        private_response(response)
        return result

    return router
