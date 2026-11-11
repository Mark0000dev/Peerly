import json

from studymate.export_openapi import build_schema


async def test_exact_chat_media_contract_and_audit_source_fields_are_exported() -> None:
    schema = json.dumps(await build_schema(), sort_keys=True)
    assert (
        '"/api/v1/operator/accounts/{account_id}/chat-image-uploads/{image_id}/attempts/{attempt_id}/{kind}"'
        in schema
    )
    for field in (
        "read_chat_media",
        "chat_media",
        "requested_chat_owner_id",
        "requested_chat_attempt_id",
        "requested_chat_kind",
        "actual_source_image_id",
    ):
        assert f'"{field}"' in schema
