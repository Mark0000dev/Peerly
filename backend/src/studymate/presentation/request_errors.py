"""Authentication input errors never echo private request values."""

from http import HTTPStatus

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

from studymate.presentation.problems import FieldProblem, problem

SAFE_FIELDS = frozenset(
    {"email", "resend_of", "code", "challenge_id", "context_id", "kind", "version"}
)


async def validation_problem(_request: Request, error: Exception) -> JSONResponse:
    if not isinstance(error, RequestValidationError):
        raise error
    fields = []
    for detail in error.errors():
        location: object = detail.get("loc")
        name = "request"
        if isinstance(location, (tuple, list)) and location:
            candidate: object = location[-1]
            if isinstance(candidate, str) and candidate in SAFE_FIELDS:
                name = candidate
        fields.append(FieldProblem((name,), "invalid_field"))
    return problem(HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_fields", errors=tuple(fields))
