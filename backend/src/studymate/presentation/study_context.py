from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Header, Request, Response
from starlette.responses import JSONResponse

from studymate.application.idempotency import IntentKey
from studymate.application.identity.browser import BrowserTokenSigner
from studymate.application.profiles.goals import (
    CompleteGoalCommand,
    CompleteOwnGoal,
    GoalVersionConflictError,
    ReadOwnGoal,
    SaveGoalCommand,
    SaveOwnGoal,
    SubjectUnavailableError,
)
from studymate.application.profiles.help_subjects import (
    HelpVersionConflictError,
    ReadOwnHelpSubjects,
    SaveHelpCommand,
    SaveOwnHelpSubjects,
)
from studymate.domain.study_context import (
    CanonicalSubjectRef,
    CustomSubjectRef,
    GoalContent,
    HelpSubject,
    HelpSubjects,
)
from studymate.presentation.browser import (
    SESSION_AUTH,
    SESSION_COOKIE,
    BrowserConfiguration,
    IdempotentWriteHeaders,
    read_cookie,
    write_credential,
)
from studymate.presentation.problems import FieldProblem, ProblemResponse, problem
from studymate.presentation.student_errors import STUDENT_ERRORS, student_problem
from studymate.presentation.study_models import (
    CanonicalSubjectRequest,
    CompleteGoalRequest,
    GoalResponse,
    HelpResponse,
    OwnGoalResponse,
    OwnHelpResponse,
    SaveGoalRequest,
    SaveHelpRequest,
    goal_response,
    help_response,
)

STUDY_ERRORS = (
    *STUDENT_ERRORS,
    GoalVersionConflictError,
    HelpVersionConflictError,
    SubjectUnavailableError,
)


@dataclass(frozen=True, slots=True)
class StudyServices:
    save_goal: SaveOwnGoal
    complete_goal: CompleteOwnGoal
    read_goal: ReadOwnGoal
    save_help: SaveOwnHelpSubjects
    read_help: ReadOwnHelpSubjects
    signer: BrowserTokenSigner
    browser: BrowserConfiguration


def _error(error: Exception, field: str = "subject") -> JSONResponse:
    shared = student_problem(error)
    if shared is not None:
        return shared
    if isinstance(error, GoalVersionConflictError):
        return problem(
            HTTPStatus.CONFLICT,
            "goal_version_conflict",
            {
                "current_goal_id": str(error.current_id) if error.current_id is not None else None,
                "current_version": error.current_version,
            },
        )
    if isinstance(error, HelpVersionConflictError):
        return problem(
            HTTPStatus.CONFLICT, "help_version_conflict", {"current_version": error.current_version}
        )
    if isinstance(error, SubjectUnavailableError):
        return problem(
            HTTPStatus.CONFLICT,
            "subject_unavailable",
            errors=(FieldProblem((field,), "unavailable_selection"),),
        )
    raise error


def _router() -> APIRouter:
    return APIRouter(
        prefix="/api/v1",
        tags=["study-context"],
        dependencies=[SESSION_AUTH],
        responses={
            status.value: {"model": ProblemResponse}
            for status in (
                HTTPStatus.BAD_REQUEST,
                HTTPStatus.UNAUTHORIZED,
                HTTPStatus.FORBIDDEN,
                HTTPStatus.CONFLICT,
                HTTPStatus.REQUEST_TIMEOUT,
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                HTTPStatus.UNPROCESSABLE_ENTITY,
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        },
    )


def _goal_router(services: StudyServices) -> APIRouter:
    router = _router()

    @router.get("/me/goal", response_model=OwnGoalResponse)
    async def read_goal(request: Request, response: Response) -> OwnGoalResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.read_goal(credential)
        except STUDY_ERRORS as error:
            return _error(error)
        response.headers["Cache-Control"] = "no-store"
        return OwnGoalResponse(goal=goal_response(result) if result is not None else None)

    @router.put("/me/goal", response_model=GoalResponse)
    async def save_goal(
        request: Request,
        body: SaveGoalRequest,
        response: Response,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> GoalResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        subject = (
            CanonicalSubjectRef(body.subject.id)
            if isinstance(body.subject, CanonicalSubjectRequest)
            else CustomSubjectRef(body.subject.label)
        )
        try:
            command = SaveGoalCommand(
                credential,
                GoalContent(subject, body.topic, body.context, body.shared_learning),
                body.expected_goal_id,
                body.expected_version,
                IntentKey(headers.idempotency_key),
            )
        except ValueError:
            return problem(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                "goal_input_invalid",
                errors=(FieldProblem(("expected_version",), "inconsistent_goal_identity"),),
            )
        try:
            result = await services.save_goal(command)
        except STUDY_ERRORS as error:
            return _error(error)
        response.headers["Cache-Control"] = "no-store"
        return goal_response(result)

    @router.post("/me/goal/complete", response_model=GoalResponse)
    async def complete_goal(
        request: Request,
        body: CompleteGoalRequest,
        response: Response,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> GoalResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            result = await services.complete_goal(
                CompleteGoalCommand(
                    credential,
                    body.goal_id,
                    body.expected_version,
                    IntentKey(headers.idempotency_key),
                )
            )
        except STUDY_ERRORS as error:
            return _error(error)
        response.headers["Cache-Control"] = "no-store"
        return goal_response(result)

    return router


def _help_router(services: StudyServices) -> APIRouter:
    router = _router()

    @router.get("/me/help-subjects", response_model=OwnHelpResponse)
    async def read_help(request: Request, response: Response) -> OwnHelpResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.read_help(credential)
        except STUDY_ERRORS as error:
            return _error(error, "subjects")
        response.headers["Cache-Control"] = "no-store"
        return OwnHelpResponse(selection=help_response(result) if result is not None else None)

    @router.put("/me/help-subjects", response_model=HelpResponse)
    async def save_help(
        request: Request,
        body: SaveHelpRequest,
        response: Response,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> HelpResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        selections = HelpSubjects(
            tuple(HelpSubject(value.subject_id, value.topic_note) for value in body.subjects)
        )
        try:
            result = await services.save_help(
                SaveHelpCommand(
                    credential,
                    selections,
                    body.expected_version,
                    IntentKey(headers.idempotency_key),
                )
            )
        except STUDY_ERRORS as error:
            return _error(error, "subjects")
        response.headers["Cache-Control"] = "no-store"
        return help_response(result)

    return router


def study_router(services: StudyServices) -> APIRouter:
    router = APIRouter()
    router.include_router(_goal_router(services))
    router.include_router(_help_router(services))
    return router
