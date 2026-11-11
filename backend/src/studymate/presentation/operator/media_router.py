"""Mounted at actual70/head43; privileged attachments, no storage access URLs or keys."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from studymate.application.operator.media_read import ReadOperatorProfileMedia
from studymate.domain.operator.profile_media import (
    OperatorProfileMediaKind,
    OperatorProfileMediaRequest,
)
from studymate.presentation.browser import SESSION_AUTH, SESSION_COOKIE, read_cookie
from studymate.presentation.operator.models import ClosedModel
from studymate.presentation.operator.router import (
    OPERATOR_ERRORS,
    operator_problem,
    private_response,
)
from studymate.presentation.problems import ProblemResponse, problem


class OperatorProfileMediaQuery(ClosedModel):
    """No client role, storage reference, URL, current-version or eligibility override."""


@dataclass(frozen=True, slots=True)
class OperatorProfileMediaHttpServices:
    read: ReadOperatorProfileMedia


def operator_profile_media_router(services: OperatorProfileMediaHttpServices) -> APIRouter:
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
        "/accounts/{account_id}/photo-uploads/{upload_id}/attempts/{attempt_id}/{kind}",
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
        upload_id: UUID,
        attempt_id: UUID,
        kind: OperatorProfileMediaKind,
        _query: Annotated[OperatorProfileMediaQuery, Query()],
    ) -> Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.read(
                credential,
                OperatorProfileMediaRequest(
                    account_id,
                    upload_id,
                    attempt_id,
                    kind,
                ),
            )
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        if result is None:
            return problem(HTTPStatus.NOT_FOUND, "operator_resource_unavailable")
        original = result.kind == OperatorProfileMediaKind.ORIGINAL
        response = Response(
            result.data, media_type="application/octet-stream" if original else "image/jpeg"
        )
        private_response(response)
        response.headers["Content-Disposition"] = (
            'attachment; filename="profile-original.bin"'
            if original
            else 'attachment; filename="profile-display.jpg"'
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
        return response

    return router
