from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from studymate.application.errors import StorageUnavailableError
from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.browser import BrowserTokenSigner
from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.application.student_notifications.capabilities import ReadOwnDelivery
from studymate.application.student_notifications.subscriptions import (
    DeliveryUnavailableError,
    RegisterDeviceCommand,
    RegisterOwnDelivery,
    SubscriptionVersionError,
)
from studymate.domain.student_notifications.capabilities import DeviceState, Platform, Registration
from studymate.presentation.browser import (
    SESSION_AUTH,
    SESSION_COOKIE,
    BrowserConfiguration,
    IdempotentWriteHeaders,
    read_cookie,
    write_credential,
)
from studymate.presentation.problems import ProblemResponse, problem


class DeliveryRegistrationBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    installation_id: UUID
    platform: Platform
    enabled: bool = Field(strict=True)
    timezone: str | None = Field(max_length=100)
    endpoint: str | None = Field(default=None, max_length=4096, repr=False)
    p256dh: str | None = Field(default=None, max_length=100, repr=False)
    auth: str | None = Field(default=None, max_length=100, repr=False)
    expected_version: int = Field(ge=0, strict=True)


class DeliveryDeviceResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    installation_id: UUID
    platform: Platform
    version: int
    enabled: bool
    timezone: str | None
    material_fingerprint: str | None


class DeliveryCapabilityResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    account_id: UUID
    web: bool
    ios: bool
    android: bool
    vapid_public_key: str | None
    device: DeliveryDeviceResponse | None


def device_response(value: DeviceState) -> DeliveryDeviceResponse:
    return DeliveryDeviceResponse(
        installation_id=value.installation_id,
        platform=value.platform,
        version=value.version,
        enabled=value.enabled,
        timezone=value.timezone,
        material_fingerprint=value.material_fingerprint,
    )


@dataclass(frozen=True, slots=True)
class DeliveryHttpServices:
    read: ReadOwnDelivery
    register: RegisterOwnDelivery
    signer: BrowserTokenSigner
    browser: BrowserConfiguration


ERRORS = (
    UnauthenticatedError,
    StudentActionDeniedError,
    IdempotencyConflictError,
    SubscriptionVersionError,
    DeliveryUnavailableError,
    StorageUnavailableError,
)


def delivery_problem(error: Exception) -> JSONResponse:
    if isinstance(error, UnauthenticatedError):
        return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
    if isinstance(error, StudentActionDeniedError):
        return problem(HTTPStatus.FORBIDDEN, "student_action_denied")
    if isinstance(error, (SubscriptionVersionError, IdempotencyConflictError)):
        return problem(HTTPStatus.CONFLICT, "delivery_registration_conflict")
    if isinstance(error, (DeliveryUnavailableError, StorageUnavailableError)):
        return problem(HTTPStatus.SERVICE_UNAVAILABLE, "delivery_unavailable")
    raise error


def student_delivery_router(services: DeliveryHttpServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/me",
        tags=["student-notifications"],
        responses={status: {"model": ProblemResponse} for status in (401, 403, 409, 422, 503)},
    )

    @router.get(
        "/notification-delivery/{installation_id}",
        response_model=DeliveryCapabilityResponse,
        dependencies=[SESSION_AUTH],
    )
    async def read(
        installation_id: UUID, request: Request, response: Response
    ) -> DeliveryCapabilityResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.read(credential, installation_id)
        except ERRORS as error:
            return delivery_problem(error)
        response.headers["Cache-Control"] = "no-store"
        cap = result.capability
        return DeliveryCapabilityResponse(
            account_id=result.account_id,
            web=cap.web,
            ios=cap.ios,
            android=cap.android,
            vapid_public_key=cap.vapid_public_key,
            device=None if result.device is None else device_response(result.device),
        )

    @router.put(
        "/notification-delivery", response_model=DeliveryDeviceResponse, dependencies=[SESSION_AUTH]
    )
    async def register(
        request: Request,
        response: Response,
        body: DeliveryRegistrationBody,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> DeliveryDeviceResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            value = Registration(
                body.installation_id,
                body.platform,
                body.enabled,
                body.timezone,
                body.endpoint,
                body.p256dh,
                body.auth,
            )
            result = await services.register(
                RegisterDeviceCommand(
                    credential, value, body.expected_version, IntentKey(headers.idempotency_key)
                )
            )
        except ValueError:
            return problem(HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_delivery_registration")
        except ERRORS as error:
            return delivery_problem(error)
        response.headers["Cache-Control"] = "no-store"
        return device_response(result)

    return router
