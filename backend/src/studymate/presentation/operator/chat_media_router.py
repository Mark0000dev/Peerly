"""Unmounted privileged chat attachments; main0056 owns canonical audit integration."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from studymate.application.operator.chat_media import ReadOperatorChatMedia
from studymate.domain.operator.chat_media import (
    OperatorChatMediaKind,
    OperatorChatMediaRequest,
)
from studymate.presentation.browser import SESSION_AUTH, SESSION_COOKIE, read_cookie
from studymate.presentation.operator.models import ClosedModel
from studymate.presentation.operator.router import (
    OPERATOR_ERRORS,
    operator_problem,
    private_response,
)
from studymate.presentation.problems import ProblemResponse, problem


class OperatorChatMediaQuery(ClosedModel):
    """No client role, storage reference, URL, current-version or eligibility override."""


@dataclass(frozen=True, slots=True)
class OperatorChatMediaHttpServices:
    read: ReadOperatorChatMedia


def operator_chat_media_router(services: OperatorChatMediaHttpServices) -> APIRouter:
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

    @router.get(
        "/accounts/{account_id}/chat-image-uploads/{image_id}/attempts/{attempt_id}/{kind}",
        response_class=Response,
        responses={
            HTTPStatus.OK.value: {
                "content": {
                    "application/octet-stream": {"schema": {"type": "string", "format": "binary"}},
                    "image/jpeg": {"schema": {"type": "string", "format": "binary"}},
                }
            }
        },
    )
    async def read(
        request: Request,
        account_id: UUID,
        image_id: UUID,
        attempt_id: UUID,
        kind: OperatorChatMediaKind,
        _query: Annotated[OperatorChatMediaQuery, Query()],
    ) -> Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.read(
                credential,
                OperatorChatMediaRequest(
                    account_id,
                    image_id,
                    attempt_id,
                    kind,
                ),
            )
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        if result is None:
            return problem(HTTPStatus.NOT_FOUND, "operator_resource_unavailable")
        original = result.kind == OperatorChatMediaKind.ORIGINAL
        response = Response(
            result.data, media_type="application/octet-stream" if original else "image/jpeg"
        )
        private_response(response)
        response.headers["Content-Disposition"] = (
            'attachment; filename="chat-original.bin"'
            if original
            else 'attachment; filename="chat-display.jpg"'
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
        return response

    return router
