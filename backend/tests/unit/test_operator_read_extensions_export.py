import json

from studymate.export_openapi import build_schema


async def test_public_policy_and_retained_lifecycle_routes_are_real_root_contracts() -> None:
    schema = json.dumps(await build_schema(), sort_keys=True)
    assert '"/api/v1/policies/{kind}/versions"' in schema
    assert '"/api/v1/operator/accounts/{account_id}/lifecycle-history"' in schema
    assert '"/api/v1/operator/accounts/{account_id}/message-operations"' in schema
    assert '"/api/v1/operator/accounts/{account_id}/message-operations/{operation_id}"' in schema
    assert '"PolicyHistoryResponse"' in schema
    assert '"OperatorLifecycleHistoryResponse"' in schema
    assert '"OperatorMessageOperationsResponse"' in schema


async def test_every_validation_response_uses_the_safe_closed_problem_contract() -> None:
    schema = json.dumps(await build_schema(), sort_keys=True)
    assert '"HTTPValidationError"' not in schema
    assert '"ValidationError"' not in schema
    assert '"ProblemResponse"' in schema
