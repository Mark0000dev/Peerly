from http import HTTPStatus

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient

from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.feedback.summaries import (
    FeedbackSummaryHttpServices,
    feedback_summary_router,
)
from studymate.presentation.request_errors import validation_problem
from tests.unit.feedback.test_summaries import Store, own, public
from tests.unit.identity_store import CREDENTIAL


async def test_invalid_uuid_runtime_problem_matches_closed_openapi_contract() -> None:
    store = Store()
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(
        feedback_summary_router(FeedbackSummaryHttpServices(public(store), own(store)))
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="https://summary.test",
            cookies={SESSION_COOKIE: CREDENTIAL.value},
        ) as http,
    ):
        response = await http.get("/api/v1/people/not-a-uuid/feedback-summary")
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.json()["code"] == "invalid_fields"
    assert "not-a-uuid" not in response.text
    assert not store.queries
    schema = app.openapi()
    declared = schema["paths"]["/api/v1/people/{person_id}/feedback-summary"]["get"]["responses"][
        "422"
    ]
    assert declared["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ProblemResponse"
    }
    assert "HTTPValidationError" not in schema["components"]["schemas"]
    assert "ValidationError" not in schema["components"]["schemas"]
