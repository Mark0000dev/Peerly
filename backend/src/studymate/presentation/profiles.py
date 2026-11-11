from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Header, Request, Response
from starlette.responses import JSONResponse

from studymate.application.idempotency import IntentKey
from studymate.application.identity.browser import BrowserTokenSigner
from studymate.application.profiles.basics import (
    ProfileNameRequiredError,
    ProfileVersionConflictError,
    ReadOwnProfile,
    SaveOwnProfile,
    SaveProfileCommand,
    UnsupportedProfileLanguageError,
)
from studymate.application.profiles.reference_data import ReadProfileReferenceData
from studymate.domain.profiles import DisplayName, LanguageCode, ProfileBasics
from studymate.presentation.browser import (
    SESSION_AUTH,
    SESSION_COOKIE,
    BrowserConfiguration,
    IdempotentWriteHeaders,
    read_cookie,
    write_credential,
)
from studymate.presentation.problems import FieldProblem, ProblemResponse, problem
from studymate.presentation.profile_models import (
    CurrentPhotoResponse,
    LanguageOptionResponse,
    OwnProfileResponse,
    ProfileReferenceResponse,
    ProfileRevisionResponse,
    SaveProfileRequest,
    revision_response,
)
from studymate.presentation.student_errors import STUDENT_ERRORS, student_problem

PROFILE_ERRORS = (
    *STUDENT_ERRORS,
    ProfileVersionConflictError,
    UnsupportedProfileLanguageError,
    ProfileNameRequiredError,
)


@dataclass(frozen=True, slots=True)
class ProfileServices:
    save: SaveOwnProfile
    read: ReadOwnProfile
    reference: ReadProfileReferenceData
    signer: BrowserTokenSigner
    browser: BrowserConfiguration


def _error(error: Exception) -> JSONResponse:
    shared = student_problem(error)
    if shared is not None:
        return shared
    if isinstance(error, ProfileVersionConflictError):
        return problem(
            HTTPStatus.CONFLICT,
            "profile_version_conflict",
            {"current_version": error.current_version},
        )
    if isinstance(error, ProfileNameRequiredError):
        return problem(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "profile_name_required",
            errors=(FieldProblem(("display_name",), "required"),),
        )
    if isinstance(error, UnsupportedProfileLanguageError):
        return problem(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "profile_language_unsupported",
            errors=(FieldProblem(("languages",), "unsupported_selection"),),
        )
    raise error


def profile_router(services: ProfileServices) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1",
        tags=["profile"],
        dependencies=[SESSION_AUTH],
        responses={
            status.value: {"model": ProblemResponse}
            for status in (
                HTTPStatus.UNAUTHORIZED,
                HTTPStatus.FORBIDDEN,
                HTTPStatus.CONFLICT,
                HTTPStatus.BAD_REQUEST,
                HTTPStatus.REQUEST_TIMEOUT,
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                HTTPStatus.UNPROCESSABLE_ENTITY,
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        },
    )

    @router.get("/me/profile", response_model=OwnProfileResponse)
    async def read(request: Request, response: Response) -> OwnProfileResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            current = await services.read(credential)
        except PROFILE_ERRORS as error:
            return _error(error)
        response.headers["Cache-Control"] = "no-store"
        return OwnProfileResponse(
            profile=revision_response(current.profile) if current.profile is not None else None,
            photo=CurrentPhotoResponse(
                upload_id=current.photo.upload_id,
                version=current.photo.version,
                display_url=f"/api/v1/media/{current.photo.upload_id}/display",
            )
            if current.photo is not None
            else None,
        )

    @router.put("/me/profile", response_model=ProfileRevisionResponse)
    async def save(
        request: Request,
        body: SaveProfileRequest,
        response: Response,
        headers: Annotated[IdempotentWriteHeaders, Header()],
    ) -> ProfileRevisionResponse | Response:
        credential = await write_credential(request, services.signer, services.browser, headers)
        if isinstance(credential, JSONResponse):
            return credential
        basics = ProfileBasics(
            DisplayName(body.display_name) if body.display_name is not None else None,
            body.about,
            body.programme,
            body.year_label,
            tuple(LanguageCode(value) for value in body.languages),
        )
        try:
            result = await services.save(
                SaveProfileCommand(
                    credential,
                    basics,
                    body.task,
                    body.expected_version,
                    IntentKey(headers.idempotency_key),
                )
            )
        except PROFILE_ERRORS as error:
            return _error(error)
        response.headers["Cache-Control"] = "no-store"
        return revision_response(result)

    @router.get("/profile-reference-data", response_model=ProfileReferenceResponse)
    async def reference(
        request: Request, response: Response
    ) -> ProfileReferenceResponse | Response:
        credential = read_cookie(request, SESSION_COOKIE)
        if credential is None:
            return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
        try:
            current = await services.reference(credential)
        except PROFILE_ERRORS as error:
            return _error(error)
        response.headers["Cache-Control"] = "no-store"
        return ProfileReferenceResponse(
            languages=tuple(
                LanguageOptionResponse(code=language.code, label=language.label)
                for language in current.languages
            ),
            max_languages=current.max_languages,
            min_display_name_length=current.min_display_name_length,
            max_display_name_length=current.max_display_name_length,
            university=current.university,
        )

    return router
