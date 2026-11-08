"""Unmounted authenticated SSE factory; root owns pool/worker/runtime acceptance."""

from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Header, Request, Response
from starlette.responses import StreamingResponse

from studymate.application.changes.reads import InvalidChangeCursorError, ReadChanges
from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.presentation.browser import SESSION_AUTH, SESSION_COOKIE, read_cookie
from studymate.presentation.changes.frames import parse_change_cursor
from studymate.presentation.changes.stream import (
    ChangeStreamingResponse,
    ChangeStreamPolicy,
    change_frames,
)
from studymate.presentation.problems import ProblemResponse, problem


@dataclass(frozen=True, slots=True)
class ChangeHttpServices:
    read: ReadChanges
    policy: ChangeStreamPolicy = field(default_factory=ChangeStreamPolicy)


def changes_router(services: ChangeHttpServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1",
        tags=["changes"],
        dependencies=[SESSION_AUTH],
        responses={
            status.value: {"model": ProblemResponse}
            for status in (
                HTTPStatus.UNAUTHORIZED,
                HTTPStatus.FORBIDDEN,
                HTTPStatus.UNPROCESSABLE_ENTITY,
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        },
    )

    @router.get(
        "/events",
        response_model=None,
        response_class=StreamingResponse,
        responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
    )
    async def events(
        request: Request,
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    ) -> Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            after = parse_change_cursor(last_event_id)
            first = await services.read(credential, after)
        except InvalidChangeCursorError:
            return problem(HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_change_cursor")
        except UnauthenticatedError:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        except StudentActionDeniedError:
            return problem(HTTPStatus.FORBIDDEN, "student_action_denied")
        except StorageUnavailableError:
            response = problem(HTTPStatus.SERVICE_UNAVAILABLE, "storage_unavailable")
            response.headers["Retry-After"] = "1"
            return response
        return ChangeStreamingResponse(
            change_frames(services.read, credential, first, services.policy), services.policy
        )

    return router
