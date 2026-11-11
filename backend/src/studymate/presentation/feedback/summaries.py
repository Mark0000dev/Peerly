"""Unmounted own/public aggregate factory; no peer identity, note or reviewer disclosure."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from studymate.application.discovery.profiles import DiscoveryProfileUnavailableError
from studymate.application.feedback.summaries import (
    FeedbackSummaryView,
    ReadOwnFeedbackSummary,
    ReadPublicFeedbackSummary,
)
from studymate.domain.feedback.summary import PUBLIC_RESPONSE_THRESHOLD
from studymate.presentation.browser import SESSION_AUTH, SESSION_COOKIE, read_cookie
from studymate.presentation.feedback.router import (
    FEEDBACK_ERRORS,
    feedback_problem,
    private_response,
)
from studymate.presentation.problems import ProblemResponse, problem


class BuildingFeedbackSummaryResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    state: Literal["building"] = "building"
    responses: int = Field(ge=0, lt=PUBLIC_RESPONSE_THRESHOLD)
    publicly_visible: bool


class AvailableFeedbackSummaryResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    state: Literal["available"] = "available"
    responses: int = Field(ge=PUBLIC_RESPONSE_THRESHOLD)
    yes: int = Field(ge=0)
    maybe: int = Field(ge=0)
    no: int = Field(ge=0)
    publicly_visible: bool


FeedbackSummaryResponse = Annotated[
    BuildingFeedbackSummaryResponse | AvailableFeedbackSummaryResponse, Field(discriminator="state")
]


@dataclass(frozen=True, slots=True)
class FeedbackSummaryHttpServices:
    public: ReadPublicFeedbackSummary
    own: ReadOwnFeedbackSummary


def summary_response(
    value: FeedbackSummaryView,
) -> BuildingFeedbackSummaryResponse | AvailableFeedbackSummaryResponse:
    summary = value.summary
    if summary.building:
        return BuildingFeedbackSummaryResponse(
            responses=summary.responses, publicly_visible=value.publicly_visible
        )
    if summary.yes is None or summary.maybe is None or summary.no is None:
        raise RuntimeError("Available feedback summary lost its actual category counts")
    return AvailableFeedbackSummaryResponse(
        responses=summary.responses,
        yes=summary.yes,
        maybe=summary.maybe,
        no=summary.no,
        publicly_visible=value.publicly_visible,
    )


def feedback_summary_router(services: FeedbackSummaryHttpServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1",
        tags=["feedback"],
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

    @router.get("/people/{person_id}/feedback-summary", response_model=FeedbackSummaryResponse)
    async def public(
        request: Request, response: Response, person_id: UUID
    ) -> BuildingFeedbackSummaryResponse | AvailableFeedbackSummaryResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.public(credential, person_id)
        except DiscoveryProfileUnavailableError:
            return problem(HTTPStatus.NOT_FOUND, "person_unavailable")
        except FEEDBACK_ERRORS as error:
            return feedback_problem(error)
        private_response(response)
        return summary_response(result)

    @router.get("/me/feedback-summary", response_model=FeedbackSummaryResponse)
    async def own(
        request: Request, response: Response
    ) -> BuildingFeedbackSummaryResponse | AvailableFeedbackSummaryResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            result = await services.own(credential)
        except FEEDBACK_ERRORS as error:
            return feedback_problem(error)
        private_response(response)
        return summary_response(result)

    return router
