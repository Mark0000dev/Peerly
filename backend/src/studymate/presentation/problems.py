from dataclasses import dataclass
from http import HTTPStatus
from uuid import uuid4

from pydantic import BaseModel, ConfigDict
from starlette.responses import JSONResponse

from studymate.presentation.request_correlation import (
    RequestContext,
    current_request_id,
    current_trace_id,
)


class FieldProblemResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    path: tuple[str, ...]
    code: str


class ProblemResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    type: str
    title: str
    status: int
    code: str
    request_id: str
    trace_id: str | None
    errors: tuple[FieldProblemResponse, ...]
    recovery: dict[str, str | int | None]


@dataclass(frozen=True, slots=True)
class FieldProblem:
    path: tuple[str, ...]
    code: str


def problem(
    status: HTTPStatus,
    code: str,
    recovery: dict[str, str | int | None] | None = None,
    *,
    errors: tuple[FieldProblem, ...] = (),
    execution: RequestContext | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
        content={
            "type": "about:blank",
            "title": status.phrase,
            "status": status.value,
            "code": code,
            "request_id": str(
                execution.request_id if execution is not None else current_request_id() or uuid4()
            ),
            "trace_id": execution.trace_id if execution is not None else current_trace_id(),
            "errors": [{"path": item.path, "code": item.code} for item in errors],
            "recovery": recovery or {},
        },
    )
