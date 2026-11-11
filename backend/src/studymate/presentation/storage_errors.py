from http import HTTPStatus

from fastapi import Request
from starlette.responses import JSONResponse

from studymate.application.errors import StorageUnavailableError
from studymate.presentation.problems import problem


async def storage_problem(_request: Request, error: Exception) -> JSONResponse:
    if not isinstance(error, StorageUnavailableError):
        raise error
    return problem(HTTPStatus.SERVICE_UNAVAILABLE, "storage_unavailable")
