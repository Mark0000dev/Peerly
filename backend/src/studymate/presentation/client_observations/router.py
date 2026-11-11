from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Header, Request, Response
from starlette.responses import JSONResponse

from studymate.application.client_observations.intake import (
    AcceptClientObservations,
    ObservationActorChangedError,
    ObservationAssetError,
    ObservationBatchCommand,
    ObservationRateLimitError,
    ObservationTimeError,
)
from studymate.application.errors import StorageUnavailableError
from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.browser import BrowserTokenSigner
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.presentation.browser import (
    SESSION_AUTH,
    BrowserConfiguration,
    IdempotentWriteHeaders,
    write_credential,
)
from studymate.presentation.client_observations.models import (
    ObservationBatchBody,
    ObservationBatchResponse,
)
from studymate.presentation.problems import ProblemResponse, problem

OBSERVATION_ERRORS = (
    ObservationActorChangedError,
    ObservationAssetError,
    ObservationTimeError,
    ObservationRateLimitError,
    IdempotencyConflictError,
    UnauthenticatedError,
    StorageUnavailableError,
)


@dataclass(frozen=True, slots=True)
class ClientObservationHttpServices:
    accept: AcceptClientObservations
    signer: BrowserTokenSigner
    browser: BrowserConfiguration


def observation_problem(error: Exception) -> JSONResponse:
    if isinstance(error, ObservationActorChangedError):
        return problem(HTTPStatus.CONFLICT, "actor_changed")
    if isinstance(error, IdempotencyConflictError):
        return problem(HTTPStatus.CONFLICT, "idempotency_conflict")
    if isinstance(error, (ObservationAssetError, ObservationTimeError)):
        return problem(HTTPStatus.UNPROCESSABLE_ENTITY, "observation_invalid")
    if isinstance(error, ObservationRateLimitError):
        response = problem(HTTPStatus.TOO_MANY_REQUESTS, "observation_rate_limited")
        response.headers["Retry-After"] = str(error.retry_after)
        return response
    if isinstance(error, UnauthenticatedError):
        return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
    if isinstance(error, StorageUnavailableError):
        response = problem(HTTPStatus.SERVICE_UNAVAILABLE, "storage_unavailable")
        response.headers["Retry-After"] = "1"
        return response
    raise error


def client_observations_router(services: ClientObservationHttpServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/telemetry",
        tags=["client-observations"],
        dependencies=[SESSION_AUTH],
        responses={
            code: {"model": ProblemResponse} for code in (401, 403, 409, 413, 415, 422, 429, 503)
        },
    )

    @router.post("/events", response_model=ObservationBatchResponse)
    async def accept(
        request: Request,
        response: Response,
        body: ObservationBatchBody,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> ObservationBatchResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            receipt = await services.accept(
                ObservationBatchCommand(
                    credential,
                    body.observations(),
                    IntentKey(headers.idempotency_key),
                    body.expected_actor_id,
                    body.release_id,
                )
            )
        except OBSERVATION_ERRORS as error:
            return observation_problem(error)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return ObservationBatchResponse(
            accepted=receipt.accepted,
            duplicates=receipt.duplicates,
            received_at=receipt.received_at,
        )

    return router
