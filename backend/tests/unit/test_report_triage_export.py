import json

from studymate.export_openapi import build_schema


async def test_internal_triage_and_retained_history_factories_use_safe_root_contracts() -> None:
    schema = json.dumps(await build_schema(), sort_keys=True)
    assert '"/api/v1/operator/reports/{report_id}/triage-source"' in schema
    assert '"/api/v1/operator/reports/{report_id}/triage"' in schema
    assert '"/api/v1/operator/accounts/{account_id}/notification-preference-history"' in schema
    assert '"/api/v1/operator/accounts/{account_id}/visibility-history"' in schema
    assert (
        '"/api/v1/operator/accounts/{account_id}/relationships/{relationship_id}/block-history"'
        in schema
    )
    assert '"HTTPValidationError"' not in schema
    assert '"ValidationError"' not in schema
