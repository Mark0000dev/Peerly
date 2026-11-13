"""Additive readonly R04 factory; ordinary accept/send APIs remain unchanged."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from studymate.application.requests.response_options import ReadRequestResponseOptions
from studymate.presentation.browser import SESSION_AUTH, SESSION_COOKIE, read_cookie
from studymate.presentation.problems import ProblemResponse, problem
from studymate.presentation.requests.response_options_models import (
    RequestResponseOptionsResponse,
    ResponseOptionsQuery,
    response_options_response,
)
from studymate.presentation.requests.router import REQUEST_ERRORS, private_response, request_error


@dataclass(frozen=True, slots=True)
class ResponseOptionsHttpServices:
    read: ReadRequestResponseOptions


def response_options_router(services: ResponseOptionsHttpServices) -> APIRouter:
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
                HTTPStatus.UNPROCESSABLE_ENTITY,
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        },
    )

    @router.get("/{request_id}/response-options", response_model=RequestResponseOptionsResponse)
    async def read_options(
        request: Request,
        response: Response,
        request_id: UUID,
        _query: Annotated[ResponseOptionsQuery, Query()],
    ) -> RequestResponseOptionsResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.read(credential, request_id)
        except REQUEST_ERRORS as error:
            return request_error(error)
        private_response(response)
        return response_options_response(result)

    return router
