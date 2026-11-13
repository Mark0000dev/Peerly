"""R04 serialization always emits tags; the actual HTTP schema must require them."""

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker

from studymate.application.requests.response_options import (
    ReadRequestResponseOptions,
    suggested_options,
)
from studymate.application.requests.response_options_data import RequestResponseOptions
from studymate.infrastructure.requests.response_options import SqlResponseOptionsUnitOfWork
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from studymate.presentation.requests.response_options_models import response_options_response
from studymate.presentation.requests.response_options_router import (
    ResponseOptionsHttpServices,
    response_options_router,
)
from tests.unit.identity_store import NOW
from tests.unit.requests.response_options_store import ResponseStore


def test_actual_http_schema_requires_all_three_literal_serialized_option_tags() -> None:
    # Construct the real router without a bound engine, credentials or provider.
    app = FastAPI()
    app.include_router(
        response_options_router(
            ResponseOptionsHttpServices(
                ReadRequestResponseOptions(
                    SqlResponseOptionsUnitOfWork(async_sessionmaker()), Sha256SessionHasher()
                )
            )
        )
    )
    schemas = app.openapi()["components"]["schemas"]
    expected = {
        "learning_too": "LearningTooOptionResponse",
        "swap": "SwapOptionResponse",
        "write_my_own": "WriteOwnOptionResponse",
    }
    mapping = schemas["ResponseOptionResponse"]["discriminator"]
    assert mapping["propertyName"] == "kind"
    assert mapping["mapping"] == {
        kind: f"#/components/schemas/{model}" for kind, model in expected.items()
    }
    for kind, model in expected.items():
        schema = schemas[model]
        assert "kind" in schema["required"]
        assert schema["properties"]["kind"]["const"] == kind
        assert schema["properties"]["kind"]["default"] == kind
    # Existing frozen option construction and default tag emission remain valid.
    context = ResponseStore().context
    value = RequestResponseOptions(
        context.request.id,
        context.request.version,
        context.request.context.sender_id,
        NOW,
        context.request.expires_at,
        "learning_too",
        suggested_options(context),
    )
    serialized = response_options_response(value).model_dump(mode="json")
    assert tuple(option["kind"] for option in serialized["options"]) == tuple(expected)
    assert serialized["default_choice"] == serialized["options"][0]["kind"]
