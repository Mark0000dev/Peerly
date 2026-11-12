import json

from studymate.export_openapi import build_schema


async def test_root_operator_manual_membership_contract_preserves_actual_proof() -> None:
    schema = json.dumps(await build_schema(), sort_keys=True)
    assert '"/api/v1/operator/accounts/{account_id}/membership-verification"' in schema
    assert '"/api/v1/operator/accounts/{account_id}/membership-verifications"' in schema
    assert '"expected_google_identity_id"' in schema
    assert '"expected_challenge_id"' in schema
    assert '"expected_email"' in schema
    assert '"manual_operator_attestation"' in schema
    assert '"otp_consumed"' in schema
    assert '"activation_granted"' in schema
    assert '"SessionCookie"' in schema
