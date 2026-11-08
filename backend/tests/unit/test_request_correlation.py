import asyncio
import json
from http import HTTPStatus
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.responses import JSONResponse
from starlette.types import Message, Receive, Scope, Send

from studymate.application.ports.http_observer import HttpObservation
from studymate.infrastructure.observability.http import JsonHttpObserver
from studymate.infrastructure.observability.logging import SafeJsonFormatter
from studymate.presentation.problems import problem
from studymate.presentation.request_correlation import RequestCorrelation, current_request_id

PRIVATE = "private-query-body-cookie-credential"


class RecordingObserver:
    def __init__(self) -> None:
        self.observations: list[HttpObservation] = []

    def completed(self, observation: HttpObservation) -> None:
        self.observations.append(observation)


def application(observer: RecordingObserver | JsonHttpObserver) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestCorrelation, observer=observer)

    @app.get("/items/{item_id}")
    async def item(item_id: UUID) -> JSONResponse:
        assert item_id.int > 0
        assert current_request_id() is not None
        await asyncio.sleep(0)
        return problem(HTTPStatus.NOT_FOUND, "item_unavailable")

    return app


async def test_concurrent_attempts_have_distinct_server_ids_and_consistent_problem_headers() -> (
    None
):
    observer = RecordingObserver()
    app = application(observer)
    client_id, action_id = uuid4(), uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        responses = await asyncio.gather(
            *(
                client.get(
                    f"/items/{uuid4()}",
                    headers={"X-Request-ID": str(client_id), "X-Action-ID": str(action_id)},
                )
                for _ in range(2)
            )
        )
    observed_ids = {str(observation.request_id) for observation in observer.observations}
    assert len(observed_ids) == len(responses)
    assert str(client_id) not in observed_ids
    for response in responses:
        assert response.headers["x-request-id"] == response.json()["request_id"]
        assert response.json()["request_id"] in observed_ids
    assert all(observation.action_id == action_id for observation in observer.observations)
    assert all(observation.route == "/items/{item_id}" for observation in observer.observations)
    assert current_request_id() is None


@pytest.mark.parametrize(
    "headers",
    [
        [("X-Action-ID", PRIVATE)],
        [("X-Action-ID", "x" * 36)],
        [("X-Action-ID", str(uuid4())), ("X-Action-ID", str(uuid4()))],
    ],
)
async def test_invalid_untrusted_correlation_is_ignored(headers: list[tuple[str, str]]) -> None:
    observer = RecordingObserver()
    async with AsyncClient(
        transport=ASGITransport(app=application(observer)), base_url="http://test"
    ) as client:
        response = await client.get("/unmatched/" + PRIVATE, headers=headers)
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert observer.observations[-1].route is None
    assert observer.observations[-1].action_id is None


async def test_exported_http_log_contains_route_template_without_url_query_or_cookie(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO", logger="studymate.http")
    resource_id = uuid4()
    async with AsyncClient(
        transport=ASGITransport(app=application(JsonHttpObserver())), base_url="http://test"
    ) as client:
        response = await client.get(
            f"/items/{resource_id}?code={PRIVATE}", headers={"Cookie": PRIVATE}
        )
    records = [record for record in caplog.records if record.name == "studymate.http"]
    output = SafeJsonFormatter().format(records[-1])
    assert PRIVATE not in output
    assert str(resource_id) not in output
    content = json.loads(output)
    assert content["route"] == "/items/{item_id}"
    assert content["method"] == "GET"
    assert content["status"] == HTTPStatus.NOT_FOUND
    assert content["request_id"] == response.headers["x-request-id"]


@pytest.mark.parametrize("cancelled", [True, False])
async def test_context_resets_after_cancellation_or_unhandled_error(cancelled: bool) -> None:
    observer = RecordingObserver()

    async def failing(_scope: Scope, _receive: Receive, _send: Send) -> None:
        assert current_request_id() is not None
        if cancelled:
            raise asyncio.CancelledError
        raise ValueError(PRIVATE)

    async def receive() -> Message:
        raise AssertionError("Unexpected receive")

    async def send(_message: Message) -> None:
        raise AssertionError("Unexpected send")

    app = RequestCorrelation(failing, observer)
    expected = asyncio.CancelledError if cancelled else ValueError
    with pytest.raises(expected):
        await app({"type": "http", "method": "UNTRUSTED", "headers": []}, receive, send)
    assert observer.observations[-1].method == "OTHER"
    assert observer.observations[-1].status == (499 if cancelled else 500)
    assert current_request_id() is None


async def test_non_http_scope_passes_through_without_execution_context() -> None:
    observer = RecordingObserver()
    passed: list[bool] = []

    async def inner(scope: Scope, _receive: Receive, _send: Send) -> None:
        assert scope["type"] == "lifespan"
        assert current_request_id() is None
        passed.append(True)

    async def receive() -> Message:
        raise AssertionError("Unexpected receive")

    async def send(_message: Message) -> None:
        raise AssertionError("Unexpected send")

    await RequestCorrelation(inner, observer)({"type": "lifespan"}, receive, send)
    assert passed == [True]
    assert not observer.observations
