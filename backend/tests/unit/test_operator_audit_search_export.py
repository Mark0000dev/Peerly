import json

from studymate.export_openapi import build_schema


async def test_actual_audit_list_contract_keeps_existing_detail_and_adds_canonical_action() -> None:
    schema = json.dumps(await build_schema(), sort_keys=True)
    assert '"/api/v1/operator/audits"' in schema
    assert '"/api/v1/operator/audits/{audit_id}"' in schema
    assert '"search_audits"' in schema
    assert '"occurred_before"' in schema
    assert '"http_request_id"' in schema
