from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from studymate.application.operator.message_operations import (
    ReadOperatorMessageOperation,
    ReadOperatorMessageOperations,
)
from studymate.presentation.browser import SESSION_AUTH, SESSION_COOKIE, read_cookie
from studymate.presentation.operator.message_operations_models import (
    OperatorMessageOperationResponse,
    OperatorMessageOperationsQuery,
    OperatorMessageOperationsResponse,
    operation_response,
    operations_response,
)
from studymate.presentation.operator.router import (
    OPERATOR_ERRORS,
    operator_problem,
    private_response,
)
from studymate.presentation.problems import ProblemResponse, problem


@dataclass(frozen=True, slots=True)
class OperatorMessageOperationsHttpServices:
    operations: ReadOperatorMessageOperations
    operation: ReadOperatorMessageOperation


def operator_message_operations_router(
    services: OperatorMessageOperationsHttpServices,
) -> APIRouter:
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
        "/accounts/{account_id}/message-operations",
        response_model=OperatorMessageOperationsResponse,
    )
    async def operations(
        request: Request,
        response: Response,
        account_id: UUID,
        query: Annotated[OperatorMessageOperationsQuery, Query()],
    ) -> OperatorMessageOperationsResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            page = await services.operations(credential, account_id, query.cursor)
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        if page is None:
            return problem(HTTPStatus.NOT_FOUND, "operator_resource_unavailable")
        private_response(response)
        return operations_response(page)

    @router.get(
        "/accounts/{account_id}/message-operations/{operation_id}",
        response_model=OperatorMessageOperationResponse,
    )
    async def operation(
        request: Request, response: Response, account_id: UUID, operation_id: UUID
    ) -> OperatorMessageOperationResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.operation(credential, account_id, operation_id)
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        if result is None:
            return problem(HTTPStatus.NOT_FOUND, "operator_resource_unavailable")
        private_response(response)
        return operation_response(result)

    return router
