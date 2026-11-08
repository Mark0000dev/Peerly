import base64
import binascii
import re
from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, ValidationInfo, field_validator

from studymate.application.catalogue import (
    MAX_PAGE_SIZE,
    CatalogueCursor,
    CatalogueQuery,
    SearchSubjects,
)
from studymate.domain.text import plain_text
from studymate.presentation.browser import SESSION_AUTH, SESSION_COOKIE, read_cookie
from studymate.presentation.problems import FieldProblem, ProblemResponse, problem
from studymate.presentation.student_errors import STUDENT_ERRORS, student_problem

MAX_CURSOR_LENGTH = 2048


class _CursorBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    normalized_name: str = Field(min_length=1, max_length=240, repr=False)
    subject_id: UUID
    query_key: str = Field(max_length=240, repr=False)

    @field_validator("normalized_name", "query_key")
    @classmethod
    def validate_plain_key(cls, value: str, info: ValidationInfo) -> str:
        return plain_text(
            value, minimum=1 if info.field_name == "normalized_name" else 0, maximum=240
        )


class InvalidCatalogueCursorError(Exception):
    pass


def encode_cursor(value: CatalogueCursor | None) -> str | None:
    if value is None:
        return None
    payload = _CursorBody(
        normalized_name=value.normalized_name,
        subject_id=value.subject_id,
        query_key=value.query_key,
    )
    return base64.urlsafe_b64encode(payload.model_dump_json().encode()).decode("ascii").rstrip("=")


def decode_cursor(value: str | None) -> CatalogueCursor | None:
    if value is None:
        return None
    if len(value) > MAX_CURSOR_LENGTH or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None:
        raise InvalidCatalogueCursorError
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        parsed = _CursorBody.model_validate_json(raw)
    except (binascii.Error, ValidationError) as error:
        raise InvalidCatalogueCursorError from error
    return CatalogueCursor(parsed.normalized_name, parsed.subject_id, parsed.query_key)


class SubjectResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID
    name: str
    aliases: tuple[str, ...]


class SubjectsResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    items: tuple[SubjectResponse, ...]
    next_cursor: str | None = Field(repr=False)


@dataclass(frozen=True, slots=True)
class CatalogueServices:
    search: SearchSubjects


def catalogue_router(services: CatalogueServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1",
        tags=["catalogue"],
        dependencies=[SESSION_AUTH],
        responses={
            status.value: {"model": ProblemResponse}
            for status in (
                HTTPStatus.BAD_REQUEST,
                HTTPStatus.UNAUTHORIZED,
                HTTPStatus.FORBIDDEN,
                HTTPStatus.UNPROCESSABLE_ENTITY,
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        },
    )

    @router.get("/subjects", response_model=SubjectsResponse)
    async def search(
        request: Request,
        response: Response,
        query: Annotated[str, Query(max_length=320)] = "",
        limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
        cursor: Annotated[str | None, Query(max_length=MAX_CURSOR_LENGTH)] = None,
    ) -> SubjectsResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            decoded = decode_cursor(cursor)
        except InvalidCatalogueCursorError:
            return problem(
                HTTPStatus.BAD_REQUEST,
                "catalogue_cursor_invalid",
                errors=(FieldProblem(("cursor",), "invalid_cursor"),),
            )
        try:
            command = CatalogueQuery(query, limit, decoded)
        except ValueError:
            field = "cursor" if cursor is not None else "query"
            return problem(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                "catalogue_query_invalid",
                errors=(FieldProblem((field,), "invalid_search"),),
            )
        try:
            page = await services.search(credential, command)
        except STUDENT_ERRORS as error:
            shared = student_problem(error)
            if shared is None:
                raise
            return shared
        response.headers["Cache-Control"] = "no-store"
        return SubjectsResponse(
            items=tuple(
                SubjectResponse(id=item.id, name=item.name, aliases=item.aliases)
                for item in page.items
            ),
            next_cursor=encode_cursor(page.next_cursor),
        )

    return router
