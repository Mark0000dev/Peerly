"""Unmounted privileged membership attestation, independent of public authentication."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response
from starlette.responses import JSONResponse

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.browser import BrowserTokenSigner
from studymate.application.operator.membership_verification import (
    ManuallyVerifyMembership,
    ManuallyVerifyMembershipCommand,
    ManualMembershipClaimConflictError,
    ManualMembershipPreconditionError,
    ManualMembershipUnavailableError,
    ReadManualMembershipContext,
)
from studymate.domain.identity import StudentEmail
from studymate.presentation.browser import (
    SESSION_AUTH,
    SESSION_COOKIE,
    BrowserConfiguration,
    IdempotentWriteHeaders,
    read_cookie,
    write_credential,
)
from studymate.presentation.operator.membership_verification_models import (
    ManualMembershipBody,
    ManualMembershipContextResponse,
    ManualMembershipResponse,
    manual_context_response,
    manual_membership_response,
)
from studymate.presentation.operator.router import (
    OPERATOR_ERRORS,
    operator_problem,
    private_response,
)
from studymate.presentation.problems import ProblemResponse, problem


def manual_membership_problem(error: Exception) -> JSONResponse:
    codes = {
        ManualMembershipUnavailableError: "manual_verification_unavailable",
        ManualMembershipPreconditionError: "manual_verification_precondition",
        ManualMembershipClaimConflictError: "institutional_email_already_claimed",
        IdempotencyConflictError: "idempotency_conflict",
    }
    return problem(HTTPStatus.CONFLICT, codes[type(error)])


@dataclass(frozen=True, slots=True)
class ManualMembershipHttpServices:
    context: ReadManualMembershipContext
    verify: ManuallyVerifyMembership
    signer: BrowserTokenSigner
    browser: BrowserConfiguration


def operator_membership_verification_router(services: ManualMembershipHttpServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/operator/accounts",
        tags=["operator"],
        dependencies=[SESSION_AUTH],
        responses={
            code: {"model": ProblemResponse} for code in (401, 403, 404, 409, 413, 415, 422, 503)
        },
    )

    @router.get(
        "/{account_id}/membership-verification", response_model=ManualMembershipContextResponse
    )
    async def context(
        account_id: UUID, request: Request, response: Response
    ) -> ManualMembershipContextResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            target = await services.context(credential, account_id)
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        if target is None:
            return problem(HTTPStatus.NOT_FOUND, "operator_resource_unavailable")
        private_response(response)
        return manual_context_response(target)

    @router.post("/{account_id}/membership-verifications", response_model=ManualMembershipResponse)
    async def verify(
        account_id: UUID,
        request: Request,
        response: Response,
        body: ManualMembershipBody,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> ManualMembershipResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            result = await services.verify(
                ManuallyVerifyMembershipCommand(
                    credential,
                    account_id,
                    body.expected_google_identity_id,
                    body.expected_challenge_id,
                    StudentEmail(body.expected_email),
                    IntentKey(headers.idempotency_key),
                )
            )
        except OPERATOR_ERRORS as error:
            return operator_problem(error)
        except (
            ManualMembershipUnavailableError,
            ManualMembershipPreconditionError,
            ManualMembershipClaimConflictError,
            IdempotencyConflictError,
        ) as error:
            return manual_membership_problem(error)
        private_response(response)
        return manual_membership_response(result)

    return router
