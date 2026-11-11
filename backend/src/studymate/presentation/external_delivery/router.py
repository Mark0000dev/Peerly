"""Exact existing operator guard and audit use cases; no unaudited inspection path."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from studymate.application.external_delivery.inspection import (
    ReadDeliverySource,
    SearchDeliverySources,
    SourceFilters,
)
from studymate.presentation.browser import SESSION_AUTH, SESSION_COOKIE, read_cookie
from studymate.presentation.external_delivery.models import (
    SourceDetailResponse,
    SourceQuery,
    SourcesResponse,
)
from studymate.presentation.operator.router import (
    OPERATOR_ERRORS,
    operator_problem,
    private_response,
)
from studymate.presentation.problems import ProblemResponse, problem


@dataclass(frozen=True, slots=True)
class ExternalDeliveryHttpServices:
    search: SearchDeliverySources
    read: ReadDeliverySource


def external_delivery_router(services: ExternalDeliveryHttpServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/operator/delivery-sources",
        tags=["operator"],
        dependencies=[SESSION_AUTH],
        responses={code: {"model": ProblemResponse} for code in (401, 403, 404, 422, 503)},
    )

    @router.get("", response_model=SourcesResponse)
    async def sources(
        request: Request, response: Response, query: Annotated[SourceQuery, Query()]
    ) -> SourcesResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            page = await services.search(
                credential, SourceFilters(query.actor_id, query.kind), query.cursor
            )
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        private_response(response)
        return SourcesResponse(sources=page.sources, next_cursor=page.next_cursor)

    @router.get("/{source_id}", response_model=SourceDetailResponse)
    async def source(
        source_id: UUID, request: Request, response: Response
    ) -> SourceDetailResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            detail = await services.read(credential, source_id)
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        if detail is None:
            return problem(HTTPStatus.NOT_FOUND, "operator_resource_unavailable")
        private_response(response)
        return SourceDetailResponse.model_validate(detail)

    return router
