"""Unexpected failures remain failures, with a sanitized correlated public response."""

import logging
from http import HTTPStatus
from uuid import uuid4

from fastapi import Request
from starlette.responses import JSONResponse

from studymate.presentation.problems import problem
from studymate.presentation.request_correlation import REQUEST_CONTEXT_KEY, RequestContext


async def unexpected_problem(request: Request, error: Exception) -> JSONResponse:
    execution: object = request.scope.get(REQUEST_CONTEXT_KEY)
    current = execution if isinstance(execution, RequestContext) else RequestContext(uuid4(), None)
    logging.getLogger("studymate.errors").error(
        "runtime_error",
        exc_info=(type(error), error, error.__traceback__),
        extra={
            "event": "runtime_error",
            "request_id": current.request_id,
            "trace_id": current.trace_id,
        },
    )
    response = problem(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", execution=current)
    response.headers["X-Request-ID"] = str(current.request_id)
    return response
