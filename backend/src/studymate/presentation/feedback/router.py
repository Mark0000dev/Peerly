"""Unmounted conversation-scoped feedback factory; main owns body bounds and export."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response
from starlette.responses import JSONResponse

from studymate.application.errors import StorageUnavailableError
from studymate.application.feedback.assessments import SaveFeedback, SaveFeedbackCommand
from studymate.application.feedback.outcomes import SaveStudyOutcome, StudyOutcomeCommand
from studymate.application.feedback.ports import (
    FeedbackVersionConflictError,
    WorkedConfirmationRequiredError,
)
from studymate.application.feedback.prompts import OfferStudyPromptOnVisit, StudyPromptVisitCommand
from studymate.application.feedback.reads import ReadOwnFeedbackContext, ReadOwnStudyOutcome
from studymate.application.idempotency import IntentKey
from studymate.application.identity.browser import BrowserTokenSigner
from studymate.application.messaging.ports import ConversationUnavailableError
from studymate.presentation.browser import (
    SESSION_AUTH,
    SESSION_COOKIE,
    BrowserConfiguration,
    IdempotentWriteHeaders,
    read_cookie,
    write_credential,
)
from studymate.presentation.feedback.models import (
    FeedbackBody,
    FeedbackReceiptResponse,
    NoStudyPromptResponse,
    OfferedStudyPromptResponse,
    OwnFeedbackResponse,
    OwnStudyOutcomeResponse,
    StudyOutcomeBody,
    StudyOutcomeResponse,
    StudyPromptVisitBody,
    context_response,
    feedback_response,
    outcome_response,
    prompt_response,
)
from studymate.presentation.problems import ProblemResponse, problem
from studymate.presentation.student_errors import STUDENT_ERRORS, student_problem

FEEDBACK_ERRORS = (
    *STUDENT_ERRORS,
    ConversationUnavailableError,
    FeedbackVersionConflictError,
    WorkedConfirmationRequiredError,
    StorageUnavailableError,
)


@dataclass(frozen=True, slots=True)
class FeedbackHttpServices:
    save_outcome: SaveStudyOutcome
    read_outcome: ReadOwnStudyOutcome
    save_feedback: SaveFeedback
    read_feedback: ReadOwnFeedbackContext
    prompt_visit: OfferStudyPromptOnVisit
    signer: BrowserTokenSigner
    browser: BrowserConfiguration


def feedback_problem(error: Exception) -> JSONResponse:
    shared = student_problem(error)
    if shared is not None:
        return shared
    if isinstance(error, StorageUnavailableError):
        response = problem(HTTPStatus.SERVICE_UNAVAILABLE, "storage_unavailable")
        response.headers["Retry-After"] = "1"
        return response
    if isinstance(error, FeedbackVersionConflictError):
        return problem(
            HTTPStatus.CONFLICT,
            "feedback_version_conflict",
            {"current_version": error.current_version},
        )
    if isinstance(error, WorkedConfirmationRequiredError):
        return problem(HTTPStatus.CONFLICT, "worked_confirmation_required")
    if isinstance(error, ConversationUnavailableError):
        return problem(HTTPStatus.NOT_FOUND, "conversation_unavailable")
    raise error


def private_response(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"


def feedback_router(services: FeedbackHttpServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/conversations",
        tags=["feedback"],
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

    @router.get("/{conversation_id}/study-outcome", response_model=OwnStudyOutcomeResponse)
    async def read_outcome(
        request: Request, response: Response, conversation_id: UUID
    ) -> OwnStudyOutcomeResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.read_outcome(credential, conversation_id)
        except FEEDBACK_ERRORS as error:
            return feedback_problem(error)
        private_response(response)
        return OwnStudyOutcomeResponse(
            outcome=outcome_response(result) if result is not None else None
        )

    @router.put("/{conversation_id}/study-outcome", response_model=StudyOutcomeResponse)
    async def save_outcome(
        request: Request,
        response: Response,
        conversation_id: UUID,
        body: StudyOutcomeBody,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> StudyOutcomeResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            result = await services.save_outcome(
                StudyOutcomeCommand(
                    credential,
                    conversation_id,
                    body.answer,
                    body.expected_version,
                    IntentKey(headers.idempotency_key),
                )
            )
        except FEEDBACK_ERRORS as error:
            return feedback_problem(error)
        private_response(response)
        return outcome_response(result)

    @router.get("/{conversation_id}/feedback", response_model=OwnFeedbackResponse)
    async def read_feedback(
        request: Request, response: Response, conversation_id: UUID
    ) -> OwnFeedbackResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.read_feedback(credential, conversation_id)
        except FEEDBACK_ERRORS as error:
            return feedback_problem(error)
        private_response(response)
        return context_response(result)

    @router.put("/{conversation_id}/feedback", response_model=FeedbackReceiptResponse)
    async def save_feedback(
        request: Request,
        response: Response,
        conversation_id: UUID,
        body: FeedbackBody,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> FeedbackReceiptResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            result = await services.save_feedback(
                SaveFeedbackCommand(
                    credential,
                    conversation_id,
                    body.content(),
                    body.expected_version,
                    IntentKey(headers.idempotency_key),
                )
            )
        except FEEDBACK_ERRORS as error:
            return feedback_problem(error)
        private_response(response)
        return feedback_response(result)

    @router.post(
        "/{conversation_id}/study-prompt-visits",
        response_model=OfferedStudyPromptResponse | NoStudyPromptResponse,
    )
    async def prompt_visit(
        request: Request,
        response: Response,
        conversation_id: UUID,
        _body: StudyPromptVisitBody,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> OfferedStudyPromptResponse | NoStudyPromptResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            result = await services.prompt_visit(
                StudyPromptVisitCommand(
                    credential, conversation_id, IntentKey(headers.idempotency_key)
                )
            )
        except FEEDBACK_ERRORS as error:
            return feedback_problem(error)
        private_response(response)
        return prompt_response(result)

    return router
