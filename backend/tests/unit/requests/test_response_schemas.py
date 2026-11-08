import pytest
from pydantic import BaseModel, ValidationError

from studymate.presentation.requests.outputs import (
    AcademicContextResponse,
    ConnectedResponse,
    GoalContextResponse,
    HelpContextResponse,
    PreviewResponse,
    RequestMutationResponse,
    ViewedResponse,
    mutation_response,
)
from studymate.presentation.requests.read_outputs import (
    RequestCapabilitiesResponse,
    RequestDetailResponse,
    RequestPageResponse,
    RequestPeerResponse,
    RequestSummaryResponse,
)
from tests.unit.requests.test_states import request

RESPONSE_TYPES: tuple[type[BaseModel], ...] = (
    GoalContextResponse,
    HelpContextResponse,
    AcademicContextResponse,
    RequestMutationResponse,
    ConnectedResponse,
    PreviewResponse,
    ViewedResponse,
    RequestCapabilitiesResponse,
    RequestPeerResponse,
    RequestSummaryResponse,
    RequestDetailResponse,
    RequestPageResponse,
)


@pytest.mark.parametrize("response_type", RESPONSE_TYPES)
def test_fixed_response_schemas_explicitly_forbid_unknown_properties(
    response_type: type[BaseModel],
) -> None:
    schema = response_type.model_json_schema()
    assert schema["additionalProperties"] is False
    definitions = schema.get("$defs")
    if isinstance(definitions, dict):
        for definition in definitions.values():
            if isinstance(definition, dict) and definition.get("type") == "object":
                assert definition["additionalProperties"] is False


def test_original_receipt_roundtrips_but_rejects_extension_fields() -> None:
    receipt = mutation_response(request(), "sent")
    payload = receipt.model_dump(mode="json")
    assert RequestMutationResponse.model_validate(payload) == receipt
    with pytest.raises(ValidationError) as error:
        RequestMutationResponse.model_validate({**payload, "invented_grant": True})
    assert error.value.errors()[0]["type"] == "extra_forbidden"
