"""Unmounted account-scoped retained conversation metadata factory."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from studymate.application.operator.conversation_index import ReadOperatorConversations
from studymate.presentation.browser import SESSION_AUTH, SESSION_COOKIE, read_cookie
from studymate.presentation.operator.conversation_index_models import (
    OperatorConversationsQuery,
    OperatorConversationsResponse,
    conversations_response,
)
from studymate.presentation.operator.router import (
    OPERATOR_ERRORS,
    operator_problem,
    private_response,
)
from studymate.presentation.problems import ProblemResponse, problem


@dataclass(frozen=True, slots=True)
class OperatorConversationIndexHttpServices:
    conversations: ReadOperatorConversations


def operator_conversation_index_router(
    services: OperatorConversationIndexHttpServices,
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/operator",
        tags=["operator"],
        dependencies=[SESSION_AUTH],
        responses={code: {"model": ProblemResponse} for code in (401, 403, 404, 422, 503)},
    )

    @router.get(
        "/accounts/{account_id}/conversations", response_model=OperatorConversationsResponse
    )
    async def conversations(
        account_id: UUID,
        request: Request,
        response: Response,
        query: Annotated[OperatorConversationsQuery, Query()],
    ) -> OperatorConversationsResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            page = await services.conversations(credential, account_id, query.cursor)
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        if page is None:
            return problem(HTTPStatus.NOT_FOUND, "operator_resource_unavailable")
        private_response(response)
        return conversations_response(page)

    return router
