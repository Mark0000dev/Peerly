from datetime import timedelta
from http import HTTPStatus

import pytest

from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.requests.cursors import InvalidRequestCursorError
from studymate.application.requests.ports import (
    RequestCooldownError,
    RequestSourceChangedError,
    RequestVersionConflictError,
)
from studymate.domain.requests.limits import RequestQuotaError
from studymate.domain.requests.states import RequestUnavailableError
from studymate.presentation.requests.router import request_error
from tests.unit.identity_store import NOW


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (UnauthenticatedError(), HTTPStatus.UNAUTHORIZED, "unauthenticated"),
        (RequestUnavailableError(), HTTPStatus.NOT_FOUND, "request_unavailable"),
        (RequestSourceChangedError(), HTTPStatus.CONFLICT, "request_source_changed"),
        (RequestQuotaError(), HTTPStatus.TOO_MANY_REQUESTS, "request_quota_exceeded"),
        (InvalidRequestCursorError(), HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_request_cursor"),
        (RequestVersionConflictError(3), HTTPStatus.CONFLICT, "request_version_changed"),
        (RequestCooldownError(NOW + timedelta(days=1)), HTTPStatus.CONFLICT, "request_cooldown"),
        (StorageUnavailableError(), HTTPStatus.SERVICE_UNAVAILABLE, "storage_unavailable"),
    ],
)
def test_expected_errors_are_safe_private_problems(
    error: Exception, status: HTTPStatus, code: str
) -> None:
    response = request_error(error)
    assert response.status_code == status
    assert code.encode() in response.body
    assert response.headers["cache-control"] == "no-store"
    if isinstance(error, (StorageUnavailableError, RequestCooldownError)):
        assert response.headers["retry-after"]
    if isinstance(error, RequestVersionConflictError):
        assert b'"current_version":3' in response.body


def test_programming_error_is_not_forged_success_or_expected_problem() -> None:
    with pytest.raises(RuntimeError, match="unexpected"):
        request_error(RuntimeError("unexpected"))
