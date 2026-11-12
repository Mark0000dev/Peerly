import json

from studymate.export_openapi import build_schema


async def test_human_review_factories_and_owner_recovery_are_mounted_root_contracts() -> None:
    schema = json.dumps(await build_schema(), sort_keys=True)
    assert '"/api/v1/me/photo-review"' in schema
    assert '"/api/v1/operator/accounts/{account_id}/photo-review"' in schema
    assert '"/api/v1/operator/accounts/{account_id}/photo-reviews"' in schema
    assert '"/api/v1/operator/reports/{report_id}/reviews"' in schema
    assert '"PhotoReviewBody"' in schema
    assert '"PhotoReviewContextResponse"' in schema
    assert '"OwnPhotoReviewResponse"' in schema
