"""Separate unmounted goal-sharing factory; main owns tested public composition."""

from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from studymate.application.idempotency import IntentKey
from studymate.application.identity.browser import BrowserTokenSigner
from studymate.application.messaging.goal_shares import (
    MAX_GOAL_SHARE_CURSOR_LENGTH,
    GoalBaselineView,
    GoalShareContextConflictError,
    GoalSharePage,
    GoalShareView,
    InvalidGoalShareCursorError,
    ReadGoalShares,
    ShareCurrentGoal,
    ShareCurrentGoalCommand,
)
from studymate.application.profiles.goals import GoalVersionConflictError
from studymate.domain.goal_shares import GoalShare
from studymate.domain.study_context import CanonicalSubjectRef
from studymate.presentation.browser import (
    SESSION_AUTH,
    SESSION_COOKIE,
    BrowserConfiguration,
    IdempotentWriteHeaders,
    read_cookie,
    write_credential,
)
from studymate.presentation.messaging.router import MESSAGE_ERRORS, message_error, private_response
from studymate.presentation.problems import ProblemResponse, problem
from studymate.presentation.requests.outputs import AcademicContextResponse, academic_context

GOAL_SHARE_ERRORS = (
    *MESSAGE_ERRORS,
    GoalVersionConflictError,
    GoalShareContextConflictError,
    InvalidGoalShareCursorError,
)


class ShareCurrentGoalBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    goal_id: UUID
    expected_goal_version: int = Field(strict=True, ge=1)
    expected_context_version: int = Field(strict=True, ge=0)


class SharedCanonicalSubjectResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["canonical"] = "canonical"
    id: UUID
    label: str = Field(repr=False)


class SharedCustomSubjectResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["custom"] = "custom"
    label: str = Field(repr=False)


class SharedGoalSourceResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    owner_id: UUID
    goal_id: UUID
    version: int
    subject: Annotated[
        SharedCanonicalSubjectResponse | SharedCustomSubjectResponse,
        Field(discriminator="kind", repr=False),
    ]
    topic: str | None = Field(repr=False)
    context: str | None = Field(repr=False)
    shared_learning: bool
    goal_created_at: datetime
    goal_updated_at: datetime


class ConversationGoalShareReceiptResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    share_id: UUID
    conversation_id: UUID
    context_version: int
    owner_id: UUID
    source: SharedGoalSourceResponse = Field(repr=False)
    shared_at: datetime


class ConversationGoalShareEntryResponse(ConversationGoalShareReceiptResponse):
    can_complete: bool


class ConversationGoalShareBaselineResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    context_version: Literal[0] = 0
    request_id: UUID
    accepted_request_version: int
    context: AcademicContextResponse = Field(repr=False)
    sender_goal_can_complete: bool
    recipient_goal_can_complete: bool


class ConversationGoalSharePageResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    baseline: ConversationGoalShareBaselineResponse = Field(repr=False)
    current_context_version: int
    anchor_version: int
    latest: ConversationGoalShareEntryResponse | None = Field(repr=False)
    history: tuple[ConversationGoalShareEntryResponse, ...] = Field(repr=False)
    next_cursor: str | None


def goal_share_receipt(value: GoalShare) -> ConversationGoalShareReceiptResponse:
    content = value.goal.content
    subject = (
        SharedCanonicalSubjectResponse(id=content.subject.id, label=value.subject_label)
        if isinstance(content.subject, CanonicalSubjectRef)
        else SharedCustomSubjectResponse(label=value.subject_label)
    )
    return ConversationGoalShareReceiptResponse(
        share_id=value.id,
        conversation_id=value.conversation_id,
        context_version=value.context_version,
        owner_id=value.owner_id,
        source=SharedGoalSourceResponse(
            owner_id=value.goal.account_id,
            goal_id=value.goal.id,
            version=value.goal.version,
            subject=subject,
            topic=content.topic,
            context=content.context,
            shared_learning=content.shared_learning,
            goal_created_at=value.goal.created_at,
            goal_updated_at=value.goal.updated_at,
        ),
        shared_at=value.shared_at,
    )


def goal_share_entry(value: GoalShareView) -> ConversationGoalShareEntryResponse:
    receipt = goal_share_receipt(value.share)
    return ConversationGoalShareEntryResponse(
        share_id=receipt.share_id,
        conversation_id=receipt.conversation_id,
        context_version=receipt.context_version,
        owner_id=receipt.owner_id,
        source=receipt.source,
        shared_at=receipt.shared_at,
        can_complete=value.can_complete,
    )


def goal_share_baseline(value: GoalBaselineView) -> ConversationGoalShareBaselineResponse:
    baseline = value.baseline
    return ConversationGoalShareBaselineResponse(
        request_id=baseline.request_id,
        accepted_request_version=baseline.accepted_request_version,
        context=academic_context(baseline.context),
        sender_goal_can_complete=value.sender_goal_can_complete,
        recipient_goal_can_complete=value.recipient_goal_can_complete,
    )


def goal_share_page(value: GoalSharePage) -> ConversationGoalSharePageResponse:
    return ConversationGoalSharePageResponse(
        baseline=goal_share_baseline(value.baseline),
        current_context_version=value.current_context_version,
        anchor_version=value.anchor_version,
        latest=goal_share_entry(value.latest) if value.latest is not None else None,
        history=tuple(goal_share_entry(entry) for entry in value.history),
        next_cursor=value.next_cursor,
    )


def goal_share_error(error: Exception) -> JSONResponse:
    if isinstance(error, GoalVersionConflictError):
        return problem(
            HTTPStatus.CONFLICT,
            "goal_version_changed",
            {
                "current_goal_id": str(error.current_id) if error.current_id is not None else None,
                "current_goal_version": error.current_version,
            },
        )
    if isinstance(error, GoalShareContextConflictError):
        return problem(
            HTTPStatus.CONFLICT,
            "conversation_goal_context_changed",
            {"current_context_version": error.current_version},
        )
    if isinstance(error, InvalidGoalShareCursorError):
        return problem(HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_goal_share_cursor")
    return message_error(error)


@dataclass(frozen=True, slots=True)
class GoalSharingHttpServices:
    share: ShareCurrentGoal
    history: ReadGoalShares
    signer: BrowserTokenSigner
    browser: BrowserConfiguration


def goal_shares_router(services: GoalSharingHttpServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/conversations",
        tags=["goal-shares"],
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

    @router.get("/{conversation_id}/goal-shares", response_model=ConversationGoalSharePageResponse)
    async def history(
        request: Request,
        conversation_id: UUID,
        response: Response,
        cursor: Annotated[str | None, Query(max_length=MAX_GOAL_SHARE_CURSOR_LENGTH)] = None,
    ) -> ConversationGoalSharePageResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = goal_share_page(await services.history(credential, conversation_id, cursor))
        except GOAL_SHARE_ERRORS as error:
            return goal_share_error(error)
        private_response(response)
        return result

    @router.post(
        "/{conversation_id}/goal-shares", response_model=ConversationGoalShareReceiptResponse
    )
    async def share(
        request: Request,
        conversation_id: UUID,
        body: ShareCurrentGoalBody,
        response: Response,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> ConversationGoalShareReceiptResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            result = goal_share_receipt(
                await services.share(
                    ShareCurrentGoalCommand(
                        credential,
                        conversation_id,
                        body.goal_id,
                        body.expected_goal_version,
                        body.expected_context_version,
                        IntentKey(headers.idempotency_key),
                    )
                )
            )
        except GOAL_SHARE_ERRORS as error:
            return goal_share_error(error)
        private_response(response)
        return result

    return router
