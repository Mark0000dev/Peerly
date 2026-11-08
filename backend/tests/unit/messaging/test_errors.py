from http import HTTPStatus

import pytest

from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.media.storage import (
    MediaObjectMissingError,
    MediaStorageUnavailableError,
)
from studymate.application.messaging.history_cursors import InvalidMessageHistoryCursorError
from studymate.application.messaging.ports import (
    ClientMessageConflictError,
    ConversationUnavailableError,
    MessageContactUnavailableError,
    MessageImageUnavailableError,
)
from studymate.presentation.messaging.router import message_error


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (UnauthenticatedError(), HTTPStatus.UNAUTHORIZED),
        (StorageUnavailableError(), HTTPStatus.SERVICE_UNAVAILABLE),
        (MediaStorageUnavailableError(), HTTPStatus.SERVICE_UNAVAILABLE),
        (ConversationUnavailableError(), HTTPStatus.NOT_FOUND),
        (MediaObjectMissingError(), HTTPStatus.NOT_FOUND),
        (MessageContactUnavailableError(), HTTPStatus.CONFLICT),
        (MessageImageUnavailableError(), HTTPStatus.CONFLICT),
        (ClientMessageConflictError(), HTTPStatus.CONFLICT),
        (InvalidMessageHistoryCursorError(), HTTPStatus.UNPROCESSABLE_ENTITY),
    ],
)
def test_expected_http_failures_are_safe_and_private(error: Exception, status: HTTPStatus) -> None:
    response = message_error(error)
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    if status == HTTPStatus.SERVICE_UNAVAILABLE:
        assert response.headers["retry-after"] == "1"


def test_unexpected_programming_errors_are_not_downgraded_to_expected_failures() -> None:
    with pytest.raises(RuntimeError, match="Unexpected"):
        message_error(RuntimeError("Unexpected"))
