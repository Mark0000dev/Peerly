from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from math import ceil
from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Path, Query, Request, Response
from starlette.responses import JSONResponse

from studymate.application.discovery.photos import ReadDiscoveryPhoto
from studymate.application.discovery.profiles import (
    DiscoveryProfileUnavailableError,
    ReadDiscoveryProfile,
)
from studymate.application.idempotency import IntentKey
from studymate.application.identity.browser import BrowserTokenSigner
from studymate.application.media.processing import InvalidImageError
from studymate.application.media.storage import (
    MediaObjectMissingError,
    MediaStorageUnavailableError,
)
from studymate.application.messaging.ports import ConversationUnavailableError
from studymate.application.safety.block_list import InvalidBlockCursorError, ReadOwnBlocks
from studymate.application.safety.blocks import (
    BlockTargetUnavailableError,
    BlockVersionConflictError,
    ChangeBlockCommand,
    ChangeOwnBlock,
)
from studymate.application.safety.message_reports import (
    IssueMessageImageReportContext,
    SubmitMessageImageReport,
    SubmitMessageImageReportCommand,
)
from studymate.application.safety.profile_reports import (
    ProfileReportRateLimitedError,
    ReportContextUnavailableError,
    SubmitProfileReport,
    SubmitProfileReportCommand,
)
from studymate.presentation.browser import (
    SESSION_AUTH,
    SESSION_COOKIE,
    BrowserConfiguration,
    IdempotentWriteHeaders,
    read_cookie,
    write_credential,
)
from studymate.presentation.message_reports import (
    MessageReportContextServices,
    message_report_context_router,
)
from studymate.presentation.people_models import (
    BlockStateResponse,
    ChangeBlockRequest,
    MessageImageReportRequest,
    OwnBlocksResponse,
    PublicProfileResponse,
    ReportReceipt,
    ReportRequest,
    block_response,
    blocks_response,
    profile_response,
    report_receipt,
)
from studymate.presentation.problems import FieldProblem, ProblemResponse, problem
from studymate.presentation.student_errors import STUDENT_ERRORS, student_problem

if TYPE_CHECKING:
    from studymate.domain.message_reports import MessageImageReport
    from studymate.domain.reports import ProfileReport


PEOPLE_ERRORS = (
    *STUDENT_ERRORS,
    DiscoveryProfileUnavailableError,
    BlockTargetUnavailableError,
    BlockVersionConflictError,
    ReportContextUnavailableError,
    ConversationUnavailableError,
    ProfileReportRateLimitedError,
    InvalidBlockCursorError,
    MediaObjectMissingError,
    MediaStorageUnavailableError,
    InvalidImageError,
)


@dataclass(frozen=True, slots=True)
class PeopleServices:
    profile: ReadDiscoveryProfile
    photo: ReadDiscoveryPhoto
    report: SubmitProfileReport
    message_report: SubmitMessageImageReport
    report_context: IssueMessageImageReportContext
    change_block: ChangeOwnBlock
    blocks: ReadOwnBlocks
    signer: BrowserTokenSigner
    browser: BrowserConfiguration


_SIMPLE_ERRORS = (
    (
        (DiscoveryProfileUnavailableError, BlockTargetUnavailableError),
        HTTPStatus.NOT_FOUND,
        "person_unavailable",
    ),
    (
        (ReportContextUnavailableError, ConversationUnavailableError),
        HTTPStatus.NOT_FOUND,
        "report_context_unavailable",
    ),
    (
        (MediaObjectMissingError, MediaStorageUnavailableError, InvalidImageError),
        HTTPStatus.SERVICE_UNAVAILABLE,
        "media_storage_unavailable",
    ),
)


def _error(error: Exception) -> JSONResponse:
    shared = student_problem(error)
    if shared is not None:
        return shared
    for kinds, status, code in _SIMPLE_ERRORS:
        if isinstance(error, kinds):
            return problem(status, code)
    if isinstance(error, BlockVersionConflictError):
        return problem(
            HTTPStatus.CONFLICT,
            "block_version_conflict",
            {"current_version": error.current_version},
        )
    if isinstance(error, InvalidBlockCursorError):
        return problem(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "invalid_cursor",
            errors=(FieldProblem(("query", "cursor"), "invalid_cursor"),),
        )
    if isinstance(error, ProfileReportRateLimitedError):
        response = problem(
            HTTPStatus.TOO_MANY_REQUESTS,
            "report_rate_limited",
            {"retry_at": error.retry_at.isoformat()},
        )
        response.headers["Retry-After"] = str(
            max(1, ceil((error.retry_at - datetime.now(UTC)).total_seconds()))
        )
        return response
    raise error


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"


def people_router(services: PeopleServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1",
        tags=["people", "safety"],
        dependencies=[SESSION_AUTH],
        responses={
            status.value: {"model": ProblemResponse}
            for status in (
                HTTPStatus.BAD_REQUEST,
                HTTPStatus.UNAUTHORIZED,
                HTTPStatus.FORBIDDEN,
                HTTPStatus.NOT_FOUND,
                HTTPStatus.CONFLICT,
                HTTPStatus.REQUEST_TIMEOUT,
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                HTTPStatus.UNPROCESSABLE_ENTITY,
                HTTPStatus.TOO_MANY_REQUESTS,
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        },
    )

    @router.get("/people/{person_id}", response_model=PublicProfileResponse)
    async def profile(
        request: Request, person_id: UUID, response: Response
    ) -> PublicProfileResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            value = await services.profile(credential, person_id)
        except PEOPLE_ERRORS as error:
            return _error(error)
        _private(response)
        return profile_response(value)

    @router.get(
        "/people/{person_id}/photo/{photo_version}",
        response_class=Response,
        responses={
            HTTPStatus.OK.value: {
                "content": {"image/jpeg": {"schema": {"type": "string", "format": "binary"}}}
            }
        },
    )
    async def photo(
        request: Request, person_id: UUID, photo_version: Annotated[int, Path(ge=1)]
    ) -> Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            data = await services.photo(credential, person_id, photo_version)
        except PEOPLE_ERRORS as error:
            return _error(error)
        return Response(
            data,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "private, no-store",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @router.get("/me/blocks", response_model=OwnBlocksResponse)
    async def blocks(
        request: Request,
        response: Response,
        cursor: Annotated[str | None, Query(max_length=512)] = None,
    ) -> OwnBlocksResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            value = await services.blocks(credential, cursor)
        except PEOPLE_ERRORS as error:
            return _error(error)
        _private(response)
        return blocks_response(value)

    @router.put("/me/blocks/{person_id}", response_model=BlockStateResponse)
    async def change_block(
        request: Request,
        person_id: UUID,
        body: ChangeBlockRequest,
        response: Response,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> BlockStateResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            value = await services.change_block(
                ChangeBlockCommand(
                    credential,
                    person_id,
                    body.blocked,
                    body.expected_version,
                    IntentKey(headers.idempotency_key),
                    body.context_id,
                )
            )
        except PEOPLE_ERRORS as error:
            return _error(error)
        _private(response)
        return block_response(value)

    @router.post("/reports", response_model=ReportReceipt, status_code=HTTPStatus.CREATED)
    async def report(
        request: Request,
        body: ReportRequest,
        response: Response,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> ReportReceipt | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        try:
            value: ProfileReport | MessageImageReport
            if isinstance(body, MessageImageReportRequest):
                value = await services.message_report(
                    SubmitMessageImageReportCommand(
                        credential,
                        body.context_id,
                        body.category,
                        IntentKey(headers.idempotency_key),
                        body.comment,
                    )
                )
            else:
                value = await services.report(
                    SubmitProfileReportCommand(
                        credential,
                        body.context_id,
                        body.category,
                        IntentKey(headers.idempotency_key),
                        body.comment,
                    )
                )
        except PEOPLE_ERRORS as error:
            return _error(error)
        _private(response)
        return report_receipt(value)

    router.include_router(
        message_report_context_router(
            MessageReportContextServices(services.report_context, services.signer, services.browser)
        )
    )
    return router
