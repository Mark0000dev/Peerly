"""Unmounted audited event/audit timeline factory; main owns root mounting/export."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from studymate.application.operator.timeline import (
    ReadOperatorAudit,
    ReadOperatorEvent,
    SearchOperatorEvents,
)
from studymate.presentation.browser import SESSION_AUTH, SESSION_COOKIE, read_cookie
from studymate.presentation.operator.router import (
    OPERATOR_ERRORS,
    operator_problem,
    private_response,
)
from studymate.presentation.operator.timeline_models import (
    OperatorAuditDetailResponse,
    OperatorEventQuery,
    OperatorEventResponse,
    OperatorEventsResponse,
    audit_response,
    event_response,
    events_response,
)
from studymate.presentation.problems import ProblemResponse, problem


@dataclass(frozen=True, slots=True)
class OperatorTimelineHttpServices:
    search: SearchOperatorEvents
    event: ReadOperatorEvent
    audit: ReadOperatorAudit


def operator_timeline_router(services: OperatorTimelineHttpServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/operator",
        tags=["operator"],
        dependencies=[SESSION_AUTH],
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

    @router.get("/events", response_model=OperatorEventsResponse)
    async def search(
        request: Request, response: Response, query: Annotated[OperatorEventQuery, Query()]
    ) -> OperatorEventsResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.search(credential, query.filters(), query.cursor)
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        private_response(response)
        return events_response(result)

    @router.get("/events/{event_id}", response_model=OperatorEventResponse)
    async def event(
        request: Request, response: Response, event_id: UUID
    ) -> OperatorEventResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.event(credential, event_id)
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        if result is None:
            return problem(HTTPStatus.NOT_FOUND, "operator_resource_unavailable")
        private_response(response)
        return event_response(result)

    @router.get("/audits/{audit_id}", response_model=OperatorAuditDetailResponse)
    async def audit(
        request: Request, response: Response, audit_id: UUID
    ) -> OperatorAuditDetailResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.audit(credential, audit_id)
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        if result is None:
            return problem(HTTPStatus.NOT_FOUND, "operator_resource_unavailable")
        private_response(response)
        return audit_response(result)

    return router
